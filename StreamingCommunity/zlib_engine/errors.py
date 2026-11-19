"""Engine error types.

Go classifies failures with ``errors.Is`` against sentinel values. Python
callers use ``except`` against the classes below instead. Wrapping an
underlying failure keeps the cause available through ``__cause__``.
"""

from __future__ import annotations

from typing import Optional


class ZlibError(Exception):
    """Base class for every engine error."""


class LoginFailed(ZlibError):
    pass


class NotLoggedIn(ZlibError):
    pass


class NoDomain(ZlibError):
    pass


class EmptyQuery(ZlibError):
    pass


class NoID(ZlibError):
    pass


class InvalidProxy(ZlibError):
    pass


class ParseFailed(ZlibError):
    pass


class SessionExpired(ZlibError):
    pass


class PhraseMinWords(ZlibError):
    pass


class Unsupported(ZlibError):
    pass


class DownloadFailed(ZlibError):
    pass


class SMTPSend(ZlibError):
    pass


class BotProtection(ZlibError):
    pass


class RedirectLoop(ZlibError):
    pass


class ChallengeFailed(ZlibError):
    pass


class MirrorUnverified(ZlibError):
    pass


class Cancelled(ZlibError):
    """The caller cancelled a long operation."""


class TransportError(ZlibError):
    """The request could not reach a response (DNS, TLS, timeout, reset)."""


class BotProtectionError(BotProtection):
    """An anti-bot page was served instead of the requested response."""

    def __init__(self, status_code: int, url: str) -> None:
        super().__init__(f"zlibrary: blocked by anti-bot protection (HTTP {status_code}) at {url}")
        self.status_code = status_code
        self.url = url


class HTTPStatusError(ZlibError):
    """An unexpected non-success HTTP response."""

    def __init__(self, status_code: int, url: str) -> None:
        super().__init__(f"zlibrary: unexpected HTTP status {status_code} at {url}")
        self.status_code = status_code
        self.url = url


def is_session_rejection(body: bytes, path: str, has_key: bool) -> bool:
    """Report whether an EAPI envelope rejects the saved session."""
    if path == "/eapi/user/login" or not has_key:
        return False
    from .text import loads_clean

    try:
        envelope = loads_clean(body)
    except ValueError:
        return False
    if not isinstance(envelope, dict):
        return False
    success = envelope.get("success")
    if not isinstance(success, int) or isinstance(success, bool) or success != 0:
        return False
    error = envelope.get("error")
    if not isinstance(error, str):
        return False
    return error.strip().lower() in {"invalid credentials", "please login"}


def is_eapi_envelope(body: bytes) -> bool:
    from .text import loads_clean

    try:
        envelope = loads_clean(body)
    except ValueError:
        return False
    return isinstance(envelope, dict) and isinstance(envelope.get("success"), int)


def optional(value: Optional[bool]) -> Optional[bool]:
    return value
