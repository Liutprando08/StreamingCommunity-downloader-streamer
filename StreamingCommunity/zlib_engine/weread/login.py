"""WeChat QR login for WeRead (mirrors ``internal/weread/login.go``)."""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
from dataclasses import dataclass, replace

from ..errors import Cancelled
from . import device
from .client import Client, Credentials, api_timeout, poll_delay, poll_timeout, qr_lifetime
from .errors import QRDeclined, QRExpired, WeReadError, api_error

QR_WAITING = 408
QR_SCANNED = 404
QR_CONFIRMED = 405
QR_EXPIRED = 402
QR_DECLINED = 403


@dataclass
class QRCode:
    uuid: str
    url: str


def ping(client: Client) -> None:
    ticket = client._get_json(
        client.api_base + "/wxticket?nonceStr=" + device.QR_NONCE,
        device.set_device_headers({}),
        timeout=api_timeout,
    )
    if not isinstance(ticket, dict) or not ticket.get("signature"):
        raise WeReadError("WeRead answered without a login ticket")


def request_qr_code(client: Client) -> QRCode:
    ticket = client._get_json(
        client.api_base + "/wxticket?nonceStr=" + device.QR_NONCE,
        device.set_device_headers({}),
        timeout=api_timeout,
    )
    if not isinstance(ticket, dict):
        raise WeReadError("WeRead QR ticket response is incomplete")
    signature = ticket.get("signature")
    timestamp = ticket.get("timeStamp")
    if not isinstance(signature, str) or not signature or timestamp in {None, ""}:
        raise WeReadError("WeRead QR ticket response is incomplete")

    query = urllib.parse.urlencode(
        sorted(
            {
                "appid": device.WECHAT_APP_ID,
                "noncestr": device.QR_NONCE,
                "timestamp": str(timestamp),
                "scope": device.WECHAT_SCOPE,
                "signature": signature,
            }.items()
        )
    )
    qr = client._get_json(
        client.open_base + "/connect/sdk/qrconnect?" + query,
        {"User-Agent": device.USER_AGENT},
        timeout=api_timeout,
    )
    if not isinstance(qr, dict):
        raise WeReadError("WeChat QR request failed (invalid response)")
    errcode = _as_int(qr.get("errcode"))
    uuid = qr.get("uuid")
    if errcode != 0 or not isinstance(uuid, str) or not uuid:
        raise WeReadError(f"WeChat QR request failed (errcode {errcode})")
    return QRCode(
        uuid=uuid,
        url=client.open_base + "/connect/confirm?uuid=" + urllib.parse.quote(uuid, safe=""),
    )


def wait_for_confirmation(
    client: Client,
    uuid: str,
    on_scanned=None,
    *,
    cancel_event=None,
) -> str:
    deadline = time.monotonic() + qr_lifetime
    scanned = False
    last = 0
    while True:
        if cancel_event is not None and cancel_event.is_set():
            raise Cancelled("operation cancelled")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise QRExpired("WeRead login QR code expired")
        state, code = _poll_once(client, uuid, last, min(poll_timeout, remaining))
        if state == QR_CONFIRMED:
            if not code:
                raise WeReadError("WeChat confirmed the login without a code")
            return code
        if state == QR_SCANNED:
            if not scanned and on_scanned is not None:
                on_scanned()
            scanned = True
        elif state == QR_WAITING:
            _sleep(poll_delay, cancel_event)
        elif state == QR_EXPIRED:
            raise QRExpired("WeRead login QR code expired")
        elif state == QR_DECLINED:
            raise QRDeclined("WeRead login was declined in WeChat")
        else:
            raise WeReadError(f"WeChat QR poll returned unknown state {state}")
        last = state


def _poll_once(client: Client, uuid: str, last: int, timeout: float) -> tuple[int, str]:
    query: dict[str, object] = {"f": "json", "uuid": uuid}
    if last:
        query["last"] = last
    url = client.long_base + "/connect/l/qrconnect?" + urllib.parse.urlencode(
        sorted(query.items())
    )
    try:
        result = client._get_json(url, {"User-Agent": "Mozilla/5.0"}, timeout=timeout)
    except (TimeoutError, urllib.error.URLError, OSError):
        return QR_WAITING, ""
    if not isinstance(result, dict):
        return QR_WAITING, ""
    code = result.get("wx_code")
    return _as_int(result.get("wx_errcode")), code if isinstance(code, str) else ""


def exchange(client: Client, code: str) -> Credentials:
    with client._lock:
        device_id = client._creds.device_id or device.new_device_id()
        timestamp = int(time.time() * 1000)
        random_value = device.random_int(1000)
        body = {
            "appFirstInstall": 1,
            "code": code,
            "deviceId": device_id,
            "deviceName": device.DEVICE_NAME,
            "deviceType": device.DEVICE_TYPE,
            "installId": device.new_install_id(),
            "isAutoLogout": 0,
            "isFromQrcode": 1,
            "random": random_value,
            "signature": device.login_signature(timestamp, device_id, random_value),
            "timestamp": timestamp,
            "trackId": "",
        }
        try:
            response = client._post_login(body)
        except WeReadError as exc:
            raise WeReadError(f"WeRead login: {exc}") from exc
        credentials = Credentials(
            vid=str(response.get("vid") or ""),
            access_token=_text(response.get("accessToken")),
            refresh_token=_text(response.get("refreshToken")),
            device_id=device_id,
        )
        if not credentials.valid():
            raise WeReadError("WeRead login returned incomplete credentials")
        client._creds = credentials
        return replace(credentials)


def _as_int(value) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _text(value) -> str:
    return value if isinstance(value, str) else ""


def _sleep(seconds: float, cancel_event) -> None:
    if cancel_event is not None:
        if cancel_event.wait(seconds):
            raise Cancelled("operation cancelled")
    else:
        time.sleep(seconds)


__all__ = [
    "QRCode",
    "ping",
    "request_qr_code",
    "wait_for_confirmation",
    "exchange",
]


# api_error is re-exported for diagnostics callers that build QR errors.
_ = api_error
