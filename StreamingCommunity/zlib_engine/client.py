"""HTTP transport and the public :class:`Client` facade.

The Go engine keeps one client with a cookie jar, a shared transport and a
single mirror domain. This module provides the same shape with ``urllib``:
cookies are scoped by :class:`http.cookiejar.CookieJar`, redirects are followed
manually so credentials can be stripped when a hop leaves the Z-Library
allowlist, and downloads can share the configured proxy.
"""

from __future__ import annotations

import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from http.cookiejar import Cookie, CookieJar
from typing import Any, Callable, Iterable, Mapping

from .constants import (
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_USER_AGENT,
    ENV_PROXY,
    ENV_RETRIES,
    MAX_REDIRECTS,
)
from .errors import (
    Cancelled,
    EmptyQuery,
    NoID,
    NotLoggedIn,
    PhraseMinWords,
    RedirectLoop,
    TransportError,
    Unsupported,
)
from .model import (
    Book,
    DownloadHistoryResult,
    DownloadResult,
    FullTextSearchOptions,
    SearchOptions,
    SearchResult,
    UserProfile,
)
from .urls import current_default_domain, normalize_domain

__all__ = ["Client", "ClientMode"]

DEFAULT_DOWNLOAD_RETRIES = 3
DEFAULT_DOWNLOAD_STALL_TIMEOUT = 120.0


class ClientMode:
    """The upstream transport used by high-level operations."""

    EAPI = "eapi"


class _LockingCookieJar(CookieJar):
    """CookieJar with a lock: the Go client serialises concurrent detail fetches."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.RLock()

    def add_cookie_header(self, request: urllib.request.Request) -> None:
        with self._lock:
            super().add_cookie_header(request)

    def extract_cookies(self, response: Any, request: urllib.request.Request) -> None:
        with self._lock:
            super().extract_cookies(response, request)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Return redirects to the caller so credentials can be handled per hop."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


class _Response:
    """Minimal response view shared by ``urlopen`` results and ``HTTPError``."""

    __slots__ = ("status", "headers", "url", "_response")

    def __init__(self, response: Any) -> None:
        self._response = response
        self.status = getattr(response, "status", None) or getattr(response, "code", 0)
        self.headers = response.headers
        self.url = getattr(response, "url", "") or getattr(response, "geturl", lambda: "")()
        if callable(self.url):
            self.url = self.url()

    def read(self, amount: int | None = None) -> bytes:
        return self._response.read(amount)

    def close(self) -> None:
        self._response.close()

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


def _as_response(result: Any) -> _Response:
    if isinstance(result, _Response):
        return result
    return _Response(result)


def _parse_retries(raw: str | None) -> int:
    if raw is None:
        return DEFAULT_DOWNLOAD_RETRIES
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        return DEFAULT_DOWNLOAD_RETRIES
    if value < 0:
        return DEFAULT_DOWNLOAD_RETRIES
    return value


def _make_cookie(name: str, value: str, domain: str, secure: bool) -> Cookie:
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=domain,
        domain_specified=True,
        domain_initial_dot=domain.startswith("."),
        path="/",
        path_specified=True,
        secure=secure,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={},
        rfc2109=False,
    )


def _origin(value: str) -> tuple[str, str] | None:
    try:
        parts = urllib.parse.urlsplit(value)
    except ValueError:
        return None
    if not parts.scheme or not parts.hostname:
        return None
    return parts.scheme.lower(), parts.hostname.lower()


def _is_allowed_origin(value: str) -> bool:
    from .domain_policy import parse_allowed_domain

    try:
        parse_allowed_domain(value)
    except ValueError:
        return False
    return True


@dataclass
class _RedirectState:
    url: str
    method: str
    data: bytes | None
    headers: dict[str, str]


class Client:
    """A Z-Library EAPI client.

    Parameters mirror the Go options: *domain* overrides the default mirror,
    *proxy* overrides ``ZLIB_PROXY`` for this client, *download_retries*
    overrides ``ZLIB_DOWNLOAD_RETRIES``. The client is thread-safe for
    concurrent book-detail fetches.
    """

    def __init__(
        self,
        domain: str | None = None,
        proxy: str | None = None,
        download_retries: int | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        proxy_value = (proxy if proxy is not None else os.environ.get(ENV_PROXY, "")).strip()
        self._proxy_value = proxy_value
        self._timeout = timeout
        self._user_agent = user_agent
        self._domain = normalize_domain(domain) or current_default_domain()
        self._mode = ClientMode.EAPI
        self._jar = _LockingCookieJar()
        self._cookies: dict[str, str] = {}
        self._cookies_lock = threading.RLock()
        self._logged_in = False
        self._cover_cache_dir = ""
        self._cover_lock = threading.RLock()
        self._download_retries = (
            download_retries
            if download_retries is not None
            else _parse_retries(os.environ.get(ENV_RETRIES))
        )
        handlers: list[Any] = [_NoRedirect(), urllib.request.HTTPCookieProcessor(self._jar)]
        if proxy_value:
            handlers.append(
                urllib.request.ProxyHandler({"http": proxy_value, "https": proxy_value})
            )
        else:
            handlers.append(urllib.request.ProxyHandler())
        self._opener = urllib.request.build_opener(*handlers)
        self._opener.addheaders = []

    # ------------------------------------------------------------------
    # Account state

    def login(self, email: str, password: str) -> None:
        from .eapi import login_eapi

        login_eapi(self, email, password)

    def logout(self) -> None:
        with self._cookies_lock:
            self._cookies = {}
            self._logged_in = False
        self._jar.clear()
        self._sync_cookies_to_jar()

    @property
    def domain(self) -> str:
        return self._domain

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        # The mobile EAPI is the only transport zlib supports.
        self._mode = ClientMode.EAPI

    @property
    def is_logged_in(self) -> bool:
        with self._cookies_lock:
            return self._logged_in

    def set_domain(self, domain: str) -> None:
        domain = normalize_domain(domain) or current_default_domain()
        self._domain = domain
        self._sync_cookies_to_jar()

    def _sync_cookies_to_jar(self) -> None:
        parts = urllib.parse.urlsplit(self._domain)
        if not parts.hostname:
            return
        secure = parts.scheme == "https"
        with self._cookies_lock:
            snapshot = dict(self._cookies)
        cookies = [
            _make_cookie(name, value, parts.hostname, secure)
            for name, value in snapshot.items()
            if name
        ]
        # http.cookiejar has no bulk setter; set_cookie is the public API.
        for cookie in cookies:
            self._jar.set_cookie(cookie)

    def cookies(self) -> dict[str, str]:
        with self._cookies_lock:
            return dict(self._cookies)

    def set_cookies(self, cookies: Mapping[str, str]) -> None:
        with self._cookies_lock:
            self._cookies = {name: value for name, value in cookies.items()}
            self._logged_in = True
        self._jar.clear()
        self._sync_cookies_to_jar()

    def close_idle_connections(self) -> None:
        """urllib has no reusable connection pool to drain; kept for parity."""

    # ------------------------------------------------------------------
    # High-level operations

    def search(
        self,
        query: str,
        page: int = 1,
        count: int = 10,
        options: SearchOptions | None = None,
    ) -> SearchResult:
        if not self.is_logged_in:
            raise NotLoggedIn("zlibrary: not logged in, call login first")
        if not query:
            raise EmptyQuery("zlibrary: search query is empty")
        count = 10 if count <= 0 else min(count, 50)
        if page <= 0:
            page = 1
        from .eapi import search_eapi

        return search_eapi(self, query, page, count, options)

    def full_text_search(
        self,
        query: str,
        page: int = 1,
        count: int = 10,
        options: FullTextSearchOptions | None = None,
    ) -> SearchResult:
        if not self.is_logged_in:
            raise NotLoggedIn("zlibrary: not logged in, call login first")
        if not query:
            raise EmptyQuery("zlibrary: search query is empty")
        if options is not None and options.phrase and len(query.split()) < 2:
            raise PhraseMinWords("zlibrary: phrase search requires at least 2 words")
        raise Unsupported(
            "zlibrary: feature unavailable in EAPI: full-text search has no verified EAPI endpoint"
        )

    def fetch_book(self, ref: str) -> Book:
        if not self.is_logged_in:
            raise NotLoggedIn("zlibrary: not logged in, call login first")
        if not ref:
            raise NoID("zlibrary: no book ID provided")
        from .eapi import fetch_book_eapi

        return fetch_book_eapi(self, ref)

    def fetch_book_details(
        self, refs: Iterable[str], *, fail_fast: bool = False
    ) -> dict[str, Book]:
        refs = list(refs)
        out: dict[str, Book] = {ref: Book() for ref in refs}
        if not refs:
            return out
        workers = min(4, len(refs))
        first_error: BaseException | None = None
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self.fetch_book, ref): ref for ref in refs}
            for future, ref in futures.items():
                try:
                    out[ref] = future.result()
                except BaseException as exc:  # noqa: BLE001 - re-raised below
                    if first_error is None:
                        first_error = exc
                    if fail_fast:
                        for pending in futures:
                            pending.cancel()
                        break
        if first_error is not None:
            raise first_error
        return out

    def recommended_books(self) -> list[Book]:
        from .endpoints import recommended_books

        return recommended_books(self)

    def most_popular_books(self) -> list[Book]:
        from .endpoints import most_popular_books

        return most_popular_books(self)

    def saved_books(self, page: int = 1) -> SearchResult:
        from .endpoints import saved_books

        return saved_books(self, page)

    def get_profile(self) -> UserProfile:
        if not self.is_logged_in:
            raise NotLoggedIn("zlibrary: not logged in, call login first")
        from .endpoints import get_profile

        return get_profile(self)

    def get_limits(self):
        return self.get_profile().download_limit

    def download_history(self, page: int = 1) -> DownloadHistoryResult:
        if not self.is_logged_in:
            raise NotLoggedIn("zlibrary: not logged in, call login first")
        from .endpoints import download_history

        return download_history(self, max(page, 1))

    def delete_download_history(self, ref: str) -> None:
        if not self.is_logged_in:
            raise NotLoggedIn("zlibrary: not logged in, call login first")
        from .endpoints import delete_download_history

        delete_download_history(self, ref)

    def download(
        self,
        download_url: str,
        dest_dir: str,
        progress: Callable[[int, int], None] | None = None,
        *,
        cancel_event: threading.Event | None = None,
    ) -> DownloadResult:
        if not self.is_logged_in:
            raise NotLoggedIn("zlibrary: not logged in, call login first")
        from .download import download

        return download(self, download_url, dest_dir, progress, cancel_event=cancel_event)

    def fetch_cover(self, raw_url: str, *, cancel_event: threading.Event | None = None):
        from .cover import fetch_cover

        return fetch_cover(self, raw_url, cancel_event=cancel_event)

    def set_cover_cache_dir(self, directory: str) -> None:
        self._cover_cache_dir = directory

    # ------------------------------------------------------------------
    # Transport used by the endpoint modules

    def _request(
        self,
        method: str,
        url: str,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        *,
        timeout: float | None = None,
        extra_cookie_header: bool = True,
    ) -> tuple[int, Any, bytes, str]:
        """Send one request, following redirects manually.

        Returns ``(status, headers, body, final_url)``. Non-2xx responses are
        returned rather than raised so EAPI error envelopes survive.
        """
        state = _RedirectState(
            url=url,
            method=method.upper(),
            data=body,
            headers=dict(headers or {}),
        )
        for redirects in range(MAX_REDIRECTS + 1):
            request = urllib.request.Request(
                state.url,
                data=state.data,
                method=state.method,
                headers=state.headers,
            )
            try:
                result = self._opener.open(request, timeout=timeout or self._timeout)
                response = _as_response(result)
            except urllib.error.HTTPError as exc:
                response = _as_response(exc)
            except urllib.error.URLError as exc:
                raise _transport_error(exc) from exc
            except (TimeoutError, OSError) as exc:
                raise _transport_error(exc) from exc

            status = int(response.status or 0)
            location = response.headers.get("Location") if response.headers else None
            if status in {301, 302, 303, 307, 308} and location:
                if redirects >= MAX_REDIRECTS:
                    response.close()
                    raise RedirectLoop(
                        f"zlibrary: too many redirects: exceeded {MAX_REDIRECTS} redirects "
                        f"while requesting {state.url}"
                    )
                new_url = urllib.parse.urljoin(state.url, location)
                if not _is_allowed_origin(new_url):
                    state.headers.pop("remix-userid", None)
                    state.headers.pop("remix-userkey", None)
                    state.headers.pop("Cookie", None)
                if status == 303 or (
                    status in {301, 302} and state.method not in {"GET", "HEAD"}
                ):
                    state.method = "GET"
                    state.data = None
                    state.headers.pop("Content-Type", None)
                    state.headers.pop("Content-Length", None)
                response.close()
                state.url = new_url
                continue

            try:
                data = response.read()
            finally:
                response.close()
            return status, response.headers, data, response.url or state.url

        raise RedirectLoop("zlibrary: too many redirects")

    def _open_stream(
        self,
        method: str,
        url: str,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        *,
        timeout: float | None = None,
    ) -> tuple[int, Any, Any, str]:
        """Open a request without reading the body (used by downloads/covers)."""
        state = _RedirectState(url, method.upper(), body, dict(headers or {}))
        for redirects in range(MAX_REDIRECTS + 1):
            request = urllib.request.Request(
                state.url, data=state.data, method=state.method, headers=state.headers
            )
            try:
                response = _as_response(self._opener.open(request, timeout=timeout or self._timeout))
            except urllib.error.HTTPError as exc:
                response = _as_response(exc)
            except urllib.error.URLError as exc:
                raise _transport_error(exc) from exc
            except (TimeoutError, OSError) as exc:
                raise _transport_error(exc) from exc

            status = int(response.status or 0)
            location = response.headers.get("Location") if response.headers else None
            if status in {301, 302, 303, 307, 308} and location:
                response.close()
                if redirects >= MAX_REDIRECTS:
                    raise RedirectLoop(
                        f"zlibrary: too many redirects: exceeded {MAX_REDIRECTS} redirects "
                        f"while requesting {state.url}"
                    )
                new_url = urllib.parse.urljoin(state.url, location)
                if not _is_allowed_origin(new_url):
                    state.headers.pop("remix-userid", None)
                    state.headers.pop("remix-userkey", None)
                    state.headers.pop("Cookie", None)
                if status == 303 or (
                    status in {301, 302} and state.method not in {"GET", "HEAD"}
                ):
                    state.method = "GET"
                    state.data = None
                    state.headers.pop("Content-Type", None)
                    state.headers.pop("Content-Length", None)
                state.url = new_url
                continue
            return status, response.headers, response, response.url or state.url
        raise RedirectLoop("zlibrary: too many redirects")


def _transport_error(exc: BaseException) -> Exception:
    reason = getattr(exc, "reason", exc)
    return TransportError(f"zlibrary: request failed: {reason}")


def check_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise Cancelled("operation cancelled: the caller cancelled the operation")


def is_retryable_status(status: int) -> bool:
    return status in {502, 503, 504}
