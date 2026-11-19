"""The WeRead e-ink client identity and request signatures."""

from __future__ import annotations

import hashlib
import secrets

DEFAULT_API_BASE = "https://i.weread.qq.com"
DEFAULT_OPEN_BASE = "https://open.weixin.qq.com"
DEFAULT_LONG_BASE = "https://long.open.weixin.qq.com"
COS_HOST_SUFFIX = ".cos.accelerate.myqcloud.com"

WECHAT_APP_ID = "wxab9b71ad2b90ff34"
WECHAT_SCOPE = "snsapi_userinfo,snsapi_timeline,snsapi_friend"
QR_NONCE = "weread"

DEVICE_NAME = "BOOX"
DEVICE_TYPE = 3

APP_VERSION = "2.1.2.10245900"
USER_AGENT = (
    "WeRead/2.1.2 WRBrand/Onyx wr_eink Dalvik/2.1.0 "
    "(Linux; U; Android 11; BOOX Build/onyx)"
)

DEVICE_ID_PREFIX = "eink334691225"
INSTALL_ID_PREFIX = "eink31"


def set_device_headers(headers: dict[str, str]) -> dict[str, str]:
    headers["User-Agent"] = USER_AGENT
    headers["baseapi"] = "30"
    headers["appver"] = APP_VERSION
    headers["basever"] = APP_VERSION
    headers["osver"] = "11"
    headers["channelId"] = "900"
    return headers


def new_device_id() -> str:
    """Return the e-ink client's device ID: prefix plus a 63-bit random number."""
    return f"{DEVICE_ID_PREFIX}{secrets.randbits(63):019d}"


def new_install_id() -> str:
    return INSTALL_ID_PREFIX + "".join(secrets.choice("0123456789") for _ in range(26))


def random_digits(count: int) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(count))


def random_int(bound: int) -> int:
    return secrets.randbelow(bound)


def login_signature(timestamp: int, device_id: str, random_value: int) -> str:
    payload = f"{timestamp}{device_id}{random_value}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
