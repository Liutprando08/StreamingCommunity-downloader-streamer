"""Send-to-Kindle over SMTP.

Mirrors ``internal/zlib/kindle.go``: implicit TLS on port 465, STARTTLS
everywhere else, a 200 MB Amazon limit, Gmail's practical 25 MB message
limit, and an attachment message built with CRLF line endings.
"""

from __future__ import annotations

import base64
import os
import smtplib
import ssl
import threading
import unicodedata
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from email.utils import format_datetime
from typing import Any

from .errors import SMTPSend

__all__ = [
    "KindleConfig",
    "SendToKindleError",
    "send_to_kindle",
    "build_kindle_message",
    "validate_kindle_attachment",
    "SMTP_SECURITY_TLS",
    "SMTP_SECURITY_STARTTLS",
]

SMTP_SECURITY_TLS = "tls"
SMTP_SECURITY_STARTTLS = "starttls"

KINDLE_MAX_FILE_SIZE = 200 * 1024 * 1024
GMAIL_MAX_MESSAGE_SIZE = 25 * 1024 * 1024
BASE64_LINE_LENGTH = 76
BASE64_LINE_BREAK = 2
KINDLE_ESTIMATED_HEADER_BYTES = 2048
KINDLE_BOUNDARY = "zlib-kindle-boundary"
ATTACHMENT_EXTENSIONS = {
    ".epub",
    ".pdf",
    ".txt",
    ".doc",
    ".docx",
    ".html",
    ".htm",
    ".rtf",
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".gif",
}
GMAIL_HOSTS = {"smtp.gmail.com", "smtp.googlemail.com"}

SMTP_DIAL_TIMEOUT = 30.0
SMTP_IDLE_TIMEOUT = 120.0


class SendToKindleError(SMTPSend):
    """A Send-to-Kindle failure with the SMTP cause preserved."""


@dataclass
class KindleConfig:
    to: str = ""
    from_: str = ""
    smtp_host: str = ""
    smtp_port: int = 0
    smtp_security: str = ""

    def security(self) -> str:
        explicit = (self.smtp_security or "").strip().lower()
        if explicit:
            return explicit
        return SMTP_SECURITY_TLS if self.smtp_port == 465 else SMTP_SECURITY_STARTTLS

    def validate(self) -> None:
        if not (self.to or "").strip():
            raise ValueError("kindle to address is required")
        if not (self.from_ or "").strip():
            raise ValueError("kindle from address is required")
        if not (self.smtp_host or "").strip():
            raise ValueError("kindle smtp host is required")
        if self.smtp_port <= 0:
            raise ValueError("kindle smtp port must be greater than 0")
        security = self.security()
        if security not in {SMTP_SECURITY_TLS, SMTP_SECURITY_STARTTLS}:
            raise ValueError(
                f'kindle smtp security must be "tls" or "starttls", not "{self.smtp_security}"'
            )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "to": self.to,
            "from": self.from_,
            "smtp_host": self.smtp_host,
            "smtp_port": self.smtp_port,
        }
        if self.smtp_security:
            data["smtp_security"] = self.smtp_security
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KindleConfig":
        port = data.get("smtp_port", 0)
        try:
            port = int(port)
        except (TypeError, ValueError):
            port = 0
        return cls(
            to=data.get("to") if isinstance(data.get("to"), str) else "",
            from_=data.get("from") if isinstance(data.get("from"), str) else "",
            smtp_host=data.get("smtp_host") if isinstance(data.get("smtp_host"), str) else "",
            smtp_port=port,
            smtp_security=(
                data.get("smtp_security") if isinstance(data.get("smtp_security"), str) else ""
            ),
        )


def is_gmail_smtp_host(host: str) -> bool:
    return (host or "").strip().lower() in GMAIL_HOSTS


def estimate_base64_message_size(file_size: int) -> int:
    if file_size <= 0:
        return 0
    encoded = ((file_size + 2) // 3) * 4
    lines = (encoded + BASE64_LINE_LENGTH - 1) // BASE64_LINE_LENGTH
    return encoded + lines * BASE64_LINE_BREAK


def validate_kindle_attachment(file_path: str, config: KindleConfig) -> None:
    extension = os.path.splitext(file_path)[1].lower()
    if extension not in ATTACHMENT_EXTENSIONS:
        if not extension:
            raise ValueError("send to kindle failed: file has no extension")
        raise ValueError(f"send to kindle failed: unsupported Send-to-Kindle file type {extension}")
    try:
        size = os.stat(file_path).st_size
    except OSError as exc:
        raise ValueError(f"send to kindle failed: {exc}") from exc
    if size > KINDLE_MAX_FILE_SIZE:
        raise ValueError(
            "send to kindle failed: file size "
            f"{size / 1024.0 / 1024.0:.2f} MB exceeds Amazon's 200 MB limit"
        )
    if is_gmail_smtp_host(config.smtp_host):
        estimated = estimate_base64_message_size(size) + KINDLE_ESTIMATED_HEADER_BYTES
        if estimated > GMAIL_MAX_MESSAGE_SIZE:
            raise ValueError(
                "send to kindle failed: file size "
                f"{size / 1024.0 / 1024.0:.2f} MB exceeds Gmail's practical 25 MB "
                "message limit for attachments"
            )


def _is_ascii(value: str) -> bool:
    return all(ord(char) <= 127 for char in value)


def _attachment_header(filename: str) -> str:
    if _is_ascii(filename):
        return f'filename="{_quote(filename)}"'
    fallback = _ascii_filename_fallback(filename)
    encoded = urllib.parse.quote(filename, safe="")
    return f'filename="{_quote(fallback)}"; filename*=UTF-8\'\'{encoded}'


def _quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _ascii_filename_fallback(filename: str) -> str:
    stem, extension = os.path.splitext(filename)
    chars: list[str] = []
    for char in stem:
        if char.isascii() and (char.isalnum() or char in "-_."):
            chars.append(char)
        else:
            chars.append("_")
    fallback = "".join(chars).strip("._")
    if not fallback:
        fallback = "attachment"
    return fallback + extension


def build_kindle_message(file_path: str, config: KindleConfig) -> bytes:
    with open(file_path, "rb") as handle:
        data = handle.read()
    filename = os.path.basename(file_path)
    attachment = _attachment_header(filename)
    now = format_datetime(datetime.now().astimezone())

    lines: list[str] = [
        f"From: {config.from_}",
        f"To: {config.to}",
        "Subject: Send to Kindle",
        f"Date: {now}",
        "MIME-Version: 1.0",
        f'Content-Type: multipart/mixed; boundary="{KINDLE_BOUNDARY}"',
        "",
        f"--{KINDLE_BOUNDARY}",
        "Content-Type: text/plain; charset=UTF-8",
        "",
        "Sent by zlib-cli.",
        "",
        f"--{KINDLE_BOUNDARY}",
        f"Content-Type: application/octet-stream; {attachment}",
        "Content-Transfer-Encoding: base64",
        f"Content-Disposition: attachment; {attachment}",
        "",
    ]
    encoded = base64.b64encode(data).decode("ascii")
    for index in range(0, len(encoded), BASE64_LINE_LENGTH):
        lines.append(encoded[index : index + BASE64_LINE_LENGTH])
    lines.append(f"--{KINDLE_BOUNDARY}--")
    lines.append("")
    return "\r\n".join(lines).encode("utf-8")


def send_to_kindle(
    file_path: str,
    config: KindleConfig,
    smtp_password: str,
    *,
    cancel_event: threading.Event | None = None,
) -> None:
    config.validate()
    if not (smtp_password or "").strip():
        raise ValueError("smtp password is required")
    validate_kindle_attachment(file_path, config)
    if cancel_event is not None and cancel_event.is_set():
        raise SendToKindleError("zlibrary: smtp send failed: cancelled")
    message = build_kindle_message(file_path, config)
    security = config.security()
    if cancel_event is not None and cancel_event.is_set():
        raise SendToKindleError("zlibrary: smtp send failed: cancelled")
    try:
        _send_mail(
            config.smtp_host,
            config.smtp_port,
            security == SMTP_SECURITY_TLS,
            config.from_,
            config.to,
            smtp_password,
            message,
        )
    except SendToKindleError:
        raise
    except Exception as exc:  # noqa: BLE001 - mapped to one public error
        address = f"{config.smtp_host}:{config.smtp_port}"
        hint = _mode_hint(security, exc)
        raise SendToKindleError(
            f"zlibrary: smtp send failed: {address} (smtp_security {security}): {exc}{hint}"
        ) from exc


def _mode_hint(security: str, exc: BaseException) -> str:
    if isinstance(exc, (TimeoutError, EOFError, ConnectionError)):
        if security == SMTP_SECURITY_STARTTLS:
            return '. If your provider lists this port as SSL/TLS, set smtp_security to "tls"'
        return ""
    if isinstance(exc, ssl.SSLError):
        if security == SMTP_SECURITY_TLS:
            return (
                ". This port does not start TLS on connect; if your provider lists it as "
                'STARTTLS, set smtp_security to "starttls"'
            )
    return ""


def _tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def _send_mail(
    host: str,
    port: int,
    implicit_tls: bool,
    sender: str,
    recipient: str,
    password: str,
    message: bytes,
) -> None:
    context = _tls_context()
    if implicit_tls:
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            host, port, timeout=SMTP_IDLE_TIMEOUT, context=context
        )
    else:
        client = smtplib.SMTP(host, port, timeout=SMTP_IDLE_TIMEOUT)
    try:
        client.ehlo()
        if not implicit_tls:
            if not client.has_extn("starttls"):
                raise SendToKindleError(
                    "zlibrary: smtp send failed: server does not offer STARTTLS; "
                    "refusing to continue without TLS"
                )
            client.starttls(context=context)
            client.ehlo()
        client.auth(
            "PLAIN",
            lambda challenge=None: f"\0{sender}\0{password}".encode("utf-8"),
        )
        client.mail(sender)
        client.rcpt(recipient)
        client.data(message)
        client.quit()
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001 - best-effort socket cleanup
            pass


# Keep unicodedata imported for callers that replicate the Go rune checks.
_ = unicodedata
