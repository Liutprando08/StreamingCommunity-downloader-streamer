"""WeRead API client skeleton: credentials, token refresh and JSON calls.

The WeRead upload endpoints are unofficial. The client identifies as the
WeRead e-ink app and never follows redirects, because the access token travels
in request headers.
"""

from __future__ import annotations

import json
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from typing import Any, Callable

from ..client import _NoRedirect
from ..text import is_bidi_control, loads_clean
from . import device
from .errors import (
    APIError,
    NotLoggedIn,
    SessionExpired,
    VerificationRequired,
    WeReadError,
    api_error,
)

MAX_RESPONSE_BYTES = 1 << 20
ERR_CODE_SESSION_EXPIRED = -2012
ERR_CODE_AUTH_FAILED = -2013
ERR_CODE_VERIFICATION = -2041

api_timeout = 30.0
qr_lifetime = 5 * 60.0
poll_timeout = 65.0
poll_delay = 1.0
upload_timeout = 30 * 60.0
notify_interval = 2.0
notify_attempts = 90
cancel_timeout = 5.0


def clean_text(value: str) -> str:
    pieces = []
    for char in value:
        if char in {"\n", "\t"}:
            pieces.append(char)
            continue
        if unicodedata.category(char) == "Cc" or is_bidi_control(char):
            continue
        pieces.append(char)
    return "".join(pieces).strip()


@dataclass
class Credentials:
    vid: str = ""
    access_token: str = ""
    refresh_token: str = ""
    device_id: str = ""
    name: str = ""

    def valid(self) -> bool:
        return bool(self.vid and self.refresh_token and self.device_id)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "vid": self.vid,
            "refresh_token": self.refresh_token,
            "device_id": self.device_id,
        }
        if self.access_token:
            data["access_token"] = self.access_token
        if self.name:
            data["name"] = self.name
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Credentials":
        def text(key: str) -> str:
            value = data.get(key)
            return value if isinstance(value, str) else ""

        return cls(
            vid=text("vid"),
            access_token=text("access_token"),
            refresh_token=text("refresh_token"),
            device_id=text("device_id"),
            name=text("name"),
        )


class _Envelope:
    __slots__ = ("code", "message")

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message


def _envelope(raw: bytes) -> _Envelope:
    try:
        data = json.loads(raw)
    except ValueError:
        return _Envelope(0, "")
    if not isinstance(data, dict):
        return _Envelope(0, "")
    code_value = data.get("errCode")
    if code_value is None:
        code_value = data.get("errcode")
    try:
        code = int(code_value) if code_value is not None else 0
    except (TypeError, ValueError):
        code = 0
    message = data.get("errMsg")
    if not isinstance(message, str) or not message:
        alt = data.get("errmsg")
        message = alt if isinstance(alt, str) else ""
    return _Envelope(code, clean_text(message))


class Client:
    """Talks to WeRead as the e-ink app. Safe for concurrent use."""

    def __init__(
        self,
        credentials: Credentials | None = None,
        save: Callable[[Credentials], None] | None = None,
        proxy: str | None = None,
        *,
        api_base: str = device.DEFAULT_API_BASE,
        open_base: str = device.DEFAULT_OPEN_BASE,
        long_base: str = device.DEFAULT_LONG_BASE,
    ) -> None:
        self.api_base = api_base
        self.open_base = open_base
        self.long_base = long_base
        self.cos_url = default_cos_url
        self._creds = credentials or Credentials()
        self._save = save
        self._lock = threading.RLock()
        handlers: list[Any] = [_NoRedirect()]
        proxy = (proxy or "").strip()
        if proxy:
            handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        else:
            handlers.append(urllib.request.ProxyHandler())
        self._opener = urllib.request.build_opener(*handlers)

    # ------------------------------------------------------------------
    # Public operations

    def credentials(self) -> Credentials:
        with self._lock:
            return replace(self._creds)

    def ping(self) -> None:
        from .login import ping

        ping(self)

    def request_qr_code(self):
        from .login import request_qr_code

        return request_qr_code(self)

    def wait_for_confirmation(self, uuid: str, on_scanned=None, *, cancel_event=None) -> str:
        from .login import wait_for_confirmation

        return wait_for_confirmation(self, uuid, on_scanned, cancel_event=cancel_event)

    def exchange(self, code: str) -> Credentials:
        from .login import exchange

        return exchange(self, code)

    def user_info(self):
        from .user import user_info

        return user_info(self)

    def update_name(self) -> str:
        from .user import update_name

        return update_name(self)

    def import_book(self, path: str, progress=None, *, cancel_event=None):
        from .importer import import_book

        return import_book(self, path, progress, cancel_event=cancel_event)

    def put_cos(self, credential, body, size: int, *, cancel_event=None) -> None:
        from .cos import put_cos

        return put_cos(self, credential, body, size, cancel_event=cancel_event)

    # ------------------------------------------------------------------
    # Transport

    def _do(self, request: urllib.request.Request, timeout: float | None = None) -> tuple[int, bytes]:
        try:
            response = self._opener.open(request, timeout=timeout or api_timeout)
        except urllib.error.HTTPError as exc:
            response = exc
        try:
            status = int(getattr(response, "status", None) or getattr(response, "code", 0) or 0)
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        finally:
            response.close()
        if len(raw) > MAX_RESPONSE_BYTES:
            raise WeReadError(
                f"WeRead {urllib.parse.urlsplit(request.full_url).path}: "
                f"response exceeds {MAX_RESPONSE_BYTES} bytes"
            )
        return status, raw

    def _send(
        self,
        method: str,
        path: str,
        query: dict[str, Any] | None = None,
        body: Any = None,
        auth: Callable[[dict[str, str]], None] | None = None,
        *,
        timeout: float | None = None,
    ) -> tuple[int, bytes]:
        url = self.api_base + path
        if query:
            encoded = urllib.parse.urlencode(sorted(query.items()), doseq=True)
            if encoded:
                url += "?" + encoded
        data = None
        headers: dict[str, str] = {}
        device.set_device_headers(headers)
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=UTF-8"
        if auth is not None:
            auth(headers)
        request = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
        return self._do(request, timeout)

    def _call(
        self,
        method: str,
        path: str,
        query: dict[str, Any] | None = None,
        body: Any = None,
        *,
        cancel_event: threading.Event | None = None,
    ) -> Any:
        for attempt in range(2):
            if cancel_event is not None and cancel_event.is_set():
                from ..errors import Cancelled

                raise Cancelled("operation cancelled")
            credentials = self._authorize(force=attempt > 0)
            status, raw = self._send(
                method,
                path,
                query,
                body,
                lambda headers, creds=credentials: _auth_headers(headers, creds),
            )
            envelope = _envelope(raw)
            if status == 401 or envelope.code in {ERR_CODE_SESSION_EXPIRED, ERR_CODE_AUTH_FAILED}:
                if attempt == 0:
                    continue
                raise SessionExpired("WeRead session expired or was revoked")
            if envelope.code == ERR_CODE_VERIFICATION:
                raise VerificationRequired(f"WeRead requires verification in its official app ({path})")
            if status != 200 or envelope.code < 0:
                raise api_error(path, status, envelope.code, envelope.message)
            if not raw:
                return None
            try:
                return loads_clean(raw)
            except ValueError as exc:
                raise WeReadError(f"WeRead {path} returned invalid JSON: {exc}") from exc
        raise SessionExpired("WeRead session expired or was revoked")

    def _authorize(self, force: bool = False) -> Credentials:
        with self._lock:
            if not self._creds.valid():
                raise NotLoggedIn("not logged in to WeRead")
            if self._creds.access_token and not force:
                return replace(self._creds)
            self._refresh_locked()
            return replace(self._creds)

    def _refresh_locked(self) -> None:
        timestamp = int(time.time() * 1000)
        random_value = device.random_int(1000) + 1
        body = {
            "deviceId": self._creds.device_id,
            "deviceName": device.DEVICE_NAME,
            "deviceType": device.DEVICE_TYPE,
            "inBackground": 0,
            "kickType": 1,
            "random": random_value,
            "refCgi": "",
            "refreshToken": self._creds.refresh_token,
            "signature": device.login_signature(timestamp, self._creds.device_id, random_value),
            "timestamp": timestamp,
            "trackId": "",
        }
        try:
            response = self._post_login(body)
        except APIError as exc:
            if exc.status < 500:
                raise SessionExpired("WeRead session expired or was revoked") from exc
            raise
        vid = str(response.get("vid") or "")
        if vid and vid != self._creds.vid:
            raise WeReadError("WeRead token refresh returned a different account")
        access_token = response.get("accessToken")
        if not isinstance(access_token, str) or not access_token:
            raise api_error("/login", 200, 0, "WeRead token refresh returned no access token")
        self._creds.access_token = access_token
        refresh_token = response.get("refreshToken")
        if isinstance(refresh_token, str) and refresh_token:
            self._creds.refresh_token = refresh_token
        if self._save is not None:
            try:
                self._save(replace(self._creds))
            except Exception as exc:  # noqa: BLE001 - preserved for the caller
                raise WeReadError(f"save WeRead credentials: {exc}") from exc

    def _post_login(self, body: dict[str, Any]) -> dict[str, Any]:
        status, raw = self._send("POST", "/login", None, body)
        envelope = _envelope(raw)
        if envelope.code == ERR_CODE_VERIFICATION:
            raise VerificationRequired("WeRead requires verification in its official app (/login)")
        try:
            response = loads_clean(raw)
        except ValueError as exc:
            raise api_error("/login", status, envelope.code, envelope.message) from exc
        access_token = response.get("accessToken") if isinstance(response, dict) else None
        if status != 200 or not isinstance(access_token, str) or not access_token:
            raise api_error("/login", status, envelope.code, envelope.message)
        return response

    def _get_json(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        request = urllib.request.Request(url, headers=headers or {})
        status, raw = self._do(request, timeout)
        if status != 200:
            raise api_error(urllib.parse.urlsplit(url).path, status)
        try:
            return loads_clean(raw)
        except ValueError as exc:
            raise WeReadError(
                f"{urllib.parse.urlsplit(url).path} returned invalid JSON: {exc}"
            ) from exc


def _auth_headers(headers: dict[str, str], credentials: Credentials) -> None:
    headers["vid"] = credentials.vid
    headers["accessToken"] = credentials.access_token


def default_cos_url(bucket: str, key: str) -> str:
    return (
        f"https://{bucket}{device.COS_HOST_SUFFIX}/"
        + urllib.parse.quote(key, safe="/")
    )


__all__ = [
    "Credentials",
    "Client",
    "clean_text",
    "default_cos_url",
    "api_timeout",
    "qr_lifetime",
    "poll_timeout",
    "poll_delay",
    "upload_timeout",
    "notify_interval",
    "notify_attempts",
    "cancel_timeout",
]
