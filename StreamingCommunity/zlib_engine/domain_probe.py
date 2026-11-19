"""Read-only health probes for Z-Library mirrors.

Redirects are followed manually so self-redirects, HTML challenges and
DiamWall interstitials can be classified precisely. No credentials are sent.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Callable, Iterable

from .client import _NoRedirect
from .constants import DEFAULT_USER_AGENT, ENV_PROXY
from .http_util import is_bot_protection_response, is_challenge_page
from .urls import normalize_domain

DOMAIN_PROBE_TIMEOUT = 10.0
MAX_DOMAIN_PROBE_REDIRECTS = 3
MAX_DOMAIN_PROBE_BODY_BYTES = 64 << 10
EAPI_DOMAINS_INFO_PATH = "/eapi/info/domains"


class DomainStatus(StrEnum):
    HEALTHY = "healthy"
    CHALLENGED = "challenged"
    DIAMWALL_BLOCKED = "diamwall_blocked"
    REDIRECT_LOOP = "redirect_loop"
    HTTP_ERROR = "http_error"
    NETWORK_ERROR = "network_error"
    INVALID_DOMAIN = "invalid_domain"


@dataclass
class DomainCheck:
    domain: str
    status: DomainStatus
    http_status: int = 0
    final_url: str = ""
    detail: str = ""
    zlib_eapi: bool = field(default=False, repr=False)

    def to_dict(self) -> dict:
        data = {"domain": self.domain, "status": str(self.status)}
        if self.http_status:
            data["http_status"] = self.http_status
        if self.final_url:
            data["final_url"] = self.final_url
        if self.detail:
            data["detail"] = self.detail
        return data


@dataclass
class DomainProbeOptions:
    proxy_url: str = ""
    path: str = ""


def known_domains() -> list[str]:
    from .domain_policy import allowed_domain_suffixes, user_mirrors

    domains = ["https://" + suffix for suffix in allowed_domain_suffixes()]
    for mirror in user_mirrors():
        if mirror not in domains:
            domains.append(mirror)
    return domains


def _opener(proxy_url: str) -> urllib.request.OpenerDirector:
    handlers: list = [_NoRedirect()]
    if proxy_url:
        handlers.append(urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url}))
    else:
        handlers.append(urllib.request.ProxyHandler())
    return urllib.request.build_opener(*handlers)


def _valid_path(path: str) -> bool:
    if not path:
        return True
    if not path.startswith("/"):
        return False
    try:
        parts = urllib.parse.urlsplit(path)
    except ValueError:
        return False
    return not parts.scheme and not parts.netloc


def probe_domain(domain: str, options: DomainProbeOptions | None = None) -> DomainCheck:
    return probe_domain_with_options(domain, options)


def probe_domain_with_options(
    domain: str, options: DomainProbeOptions | None = None
) -> DomainCheck:
    options = options or DomainProbeOptions()
    domain = normalize_domain(domain)
    result = DomainCheck(domain=domain, status=DomainStatus.INVALID_DOMAIN)
    try:
        current = urllib.parse.urlsplit(domain)
    except ValueError:
        result.detail = "domain must be an absolute HTTP URL"
        return result
    if not current.scheme or not current.hostname:
        result.detail = "domain must be an absolute HTTP URL"
        return result
    if not _valid_path(options.path):
        result.status = DomainStatus.INVALID_DOMAIN
        result.detail = "probe path must be an absolute URL path"
        return result
    if options.path:
        base = urllib.parse.urlunsplit(current)
        current = urllib.parse.urlsplit(urllib.parse.urljoin(base.rstrip("/") + "/", options.path))

    proxy_url = (options.proxy_url or "").strip() or __import__("os").environ.get(ENV_PROXY, "")
    opener = _opener(proxy_url.strip())
    deadline = time.monotonic() + DOMAIN_PROBE_TIMEOUT
    saw_diamwall_cookie = False

    def blocked_or_loop(detail: str) -> DomainCheck:
        if saw_diamwall_cookie:
            result.status = DomainStatus.DIAMWALL_BLOCKED
            result.detail = "DiamWall anti-bot redirect that never resolves"
        else:
            result.status = DomainStatus.REDIRECT_LOOP
            result.detail = detail
        return result

    seen: set[str] = set()
    redirects = 0
    while True:
        current_url = urllib.parse.urlunsplit(current)
        result.final_url = current_url
        if current_url in seen:
            return blocked_or_loop("redirected to a previously visited URL")
        seen.add(current_url)

        headers = {"User-Agent": DEFAULT_USER_AGENT}
        if options.path.startswith("/eapi/"):
            headers["Accept"] = "application/json"
        else:
            headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        request = urllib.request.Request(current_url, headers=headers)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            result.status = DomainStatus.NETWORK_ERROR
            result.detail = "probe timed out"
            return result
        try:
            try:
                response = opener.open(request, timeout=remaining)
            except urllib.error.HTTPError as exc:
                response = exc
        except urllib.error.URLError as exc:
            result.status = DomainStatus.NETWORK_ERROR
            result.detail = str(getattr(exc, "reason", exc))
            return result
        except (TimeoutError, OSError) as exc:
            result.status = DomainStatus.NETWORK_ERROR
            result.detail = str(exc)
            return result

        try:
            body = response.read(MAX_DOMAIN_PROBE_BODY_BYTES)
        except (TimeoutError, OSError) as exc:
            result.status = DomainStatus.NETWORK_ERROR
            result.detail = str(exc)
            return result
        finally:
            status = int(getattr(response, "status", None) or getattr(response, "code", 0) or 0)
            response_url = getattr(response, "url", "") or getattr(
                response, "geturl", lambda: current_url
            )()
            if callable(response_url):
                response_url = response_url()
            result.http_status = status
            result.final_url = response_url or current_url
            cookie_headers = response.headers.get_all("Set-Cookie") if response.headers else None
            response.close()

        if cookie_headers and any("__diamwall" in value.lower() for value in cookie_headers):
            saw_diamwall_cookie = True
        if is_bot_protection_response(status, response.headers, body):
            result.status = DomainStatus.DIAMWALL_BLOCKED
            result.detail = "DiamWall anti-bot response"
            return result
        if is_challenge_page(body.decode("utf-8", errors="replace")):
            result.status = DomainStatus.CHALLENGED
            result.detail = "HTML challenge; EAPI unavailable"
            return result
        if 200 <= status < 300:
            if options.path.startswith("/eapi/") and not _valid_json(body):
                result.status = DomainStatus.HTTP_ERROR
                result.detail = "EAPI returned non-JSON content"
                return result
            if options.path == EAPI_DOMAINS_INFO_PATH:
                try:
                    info = json.loads(body)
                except ValueError:
                    info = None
                result.zlib_eapi = (
                    isinstance(info, dict)
                    and info.get("success") == 1
                    and info.get("domains") is not None
                )
            result.status = DomainStatus.HEALTHY
            return result
        if not 300 <= status < 400:
            result.status = DomainStatus.HTTP_ERROR
            result.detail = f"HTTP {status}"
            return result

        location = response.headers.get("Location") if response.headers else None
        if not location:
            result.status = DomainStatus.HTTP_ERROR
            result.detail = f"HTTP {status} without a valid Location header"
            return result
        if redirects >= MAX_DOMAIN_PROBE_REDIRECTS:
            return blocked_or_loop(f"exceeded {MAX_DOMAIN_PROBE_REDIRECTS} redirects")
        redirects += 1
        try:
            current = urllib.parse.urlsplit(urllib.parse.urljoin(result.final_url, location))
        except ValueError:
            result.status = DomainStatus.HTTP_ERROR
            result.detail = "invalid redirect Location"
            return result


def _valid_json(body: bytes) -> bool:
    try:
        json.loads(body)
    except ValueError:
        return False
    return True


def probe_domains(domains: Iterable[str], options: DomainProbeOptions | None = None) -> list[DomainCheck]:
    domains = list(domains)
    return probe_domains_with_options(domains, options)


def probe_domains_with_options(
    domains: Iterable[str], options: DomainProbeOptions | None = None
) -> list[DomainCheck]:
    domains = list(domains)
    results: list[DomainCheck | None] = [None] * len(domains)
    lock = threading.Lock()

    def run(index: int, domain: str) -> None:
        check = probe_domain_with_options(domain, options)
        with lock:
            results[index] = check

    if domains:
        with ThreadPoolExecutor(max_workers=len(domains)) as pool:
            futures = [pool.submit(run, index, domain) for index, domain in enumerate(domains)]
            for future in futures:
                future.result()
    return [check for check in results if check is not None]


def probe_domains_each(
    domains: Iterable[str],
    options: DomainProbeOptions | None = None,
    each: Callable[[int, DomainCheck], None] | None = None,
) -> list[DomainCheck]:
    """Probe concurrently and invoke *each* as results complete."""
    domains = list(domains)
    results: list[DomainCheck | None] = [None] * len(domains)
    lock = threading.Lock()

    def run(index: int, domain: str) -> None:
        check = probe_domain_with_options(domain, options)
        if each is not None:
            each(index, check)
        with lock:
            results[index] = check

    if domains:
        with ThreadPoolExecutor(max_workers=len(domains)) as pool:
            futures = [pool.submit(run, index, domain) for index, domain in enumerate(domains)]
            for future in futures:
                future.result()
    return [check for check in results if check is not None]


__all__ = [
    "DomainStatus",
    "DomainCheck",
    "DomainProbeOptions",
    "EAPI_DOMAINS_INFO_PATH",
    "known_domains",
    "probe_domain",
    "probe_domain_with_options",
    "probe_domains",
    "probe_domains_with_options",
    "probe_domains_each",
]
