"""Tencent COS upload with the WeRead app's signed PUT.

Mirrors ``internal/weread/cos.go``. A single PUT accepts objects far above
WeRead's import limit, so no multipart path is needed.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from ..errors import Cancelled
from .client import Client, upload_timeout
from .errors import WeReadError

COS_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
COS_ERROR_CODE_RE = re.compile(r"<Code>([A-Za-z]{1,64})</Code>")


@dataclass
class COSCredentials:
    tmp_secret_id: str = ""
    tmp_secret_key: str = ""
    token: str = ""

    def complete(self) -> bool:
        return bool(self.tmp_secret_id and self.tmp_secret_key and self.token)

    @classmethod
    def from_api(cls, data) -> "COSCredentials":
        if not isinstance(data, dict):
            return cls()
        return cls(
            tmp_secret_id=_text(data.get("TmpSecretId")),
            tmp_secret_key=_text(data.get("TmpSecretKey")),
            token=_text(data.get("Token")),
        )


@dataclass
class UploadCredential:
    bucket: str
    key: str
    object_name: str
    credentials: COSCredentials
    expires: int


def cos_escape(value: str) -> str:
    return urllib.parse.quote_plus(value, safe="").replace("+", "%20")


def sha1_hex(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def hmac_sha1_hex(key: str, message: str) -> str:
    return hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha1).hexdigest()


def cos_authorization(
    secret_id: str,
    secret_key: str,
    method: str,
    path: str,
    headers: dict[str, str],
    start: int,
    end: int,
) -> str:
    key_time = f"{start};{end}"
    names = sorted(headers)
    pairs = [cos_escape(name) + "=" + cos_escape(headers[name]) for name in names]
    http_string = method.lower() + "\n" + path + "\n\n" + "&".join(pairs) + "\n"
    string_to_sign = "sha1\n" + key_time + "\n" + sha1_hex(http_string) + "\n"
    sign_key = hmac_sha1_hex(secret_key, key_time)
    signature = hmac_sha1_hex(sign_key, string_to_sign)
    return "&".join(
        [
            "q-sign-algorithm=sha1",
            "q-ak=" + secret_id,
            "q-sign-time=" + key_time,
            "q-key-time=" + key_time,
            "q-header-list=" + ";".join(names),
            "q-url-param-list=",
            "q-signature=" + signature,
        ]
    )


def put_cos(
    client: Client,
    credential: UploadCredential,
    body,
    size: int,
    *,
    cancel_event=None,
) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise Cancelled("operation cancelled")
    bucket, key = credential.bucket, credential.key
    creds = credential.credentials
    url = client.cos_url(bucket, key)
    request = urllib.request.Request(url, data=body, method="PUT")
    request.add_header("Content-Type", "application/octet-stream")
    request.add_header("x-cos-security-token", creds.token)
    request.add_header("Content-Length", str(size))

    now = int(time.time())
    start, end = now - 60, now + 3600
    if now < credential.expires < end:
        end = credential.expires
    authorization = cos_authorization(
        creds.tmp_secret_id,
        creds.tmp_secret_key,
        "PUT",
        "/" + key,
        {
            "content-length": str(size),
            "host": urllib.parse.urlsplit(url).netloc,
        },
        start,
        end,
    )
    request.add_header("Authorization", authorization)

    try:
        try:
            response = client._opener.open(request, timeout=upload_timeout)
        except urllib.error.HTTPError as exc:
            response = exc
        status = int(getattr(response, "status", None) or getattr(response, "code", 0) or 0)
        try:
            if status == 200:
                response.read(1 << 20)
                return
            raw = response.read(4 << 10)
        finally:
            response.close()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise WeReadError(f"COS upload: {exc}") from exc

    message = f"COS upload failed (HTTP {status})"
    match = COS_ERROR_CODE_RE.search(raw.decode("utf-8", errors="replace"))
    if match:
        message += ": " + match.group(1)
    raise WeReadError(message)


def _text(value) -> str:
    return value if isinstance(value, str) else ""


__all__ = [
    "COSCredentials",
    "UploadCredential",
    "put_cos",
    "cos_authorization",
    "cos_escape",
    "sha1_hex",
    "hmac_sha1_hex",
]
