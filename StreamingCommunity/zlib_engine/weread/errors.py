"""WeRead error types (mirrors ``internal/weread/errors.go``)."""

from __future__ import annotations

__all__ = [
    "WeReadError",
    "NotLoggedIn",
    "SessionExpired",
    "VerificationRequired",
    "QRExpired",
    "QRDeclined",
    "UnsupportedFormat",
    "FileTooLarge",
    "ImportUnconfirmed",
    "ImportParseFailed",
    "ImportLimit",
    "RateLimited",
    "APIError",
    "ImportLimitError",
    "RateLimitedError",
    "api_error",
]

ERR_CODE_IMPORT_LIMIT = -2999
ERR_CODE_RATE_LIMITED = -2014


class WeReadError(Exception):
    pass


class NotLoggedIn(WeReadError):
    pass


class SessionExpired(WeReadError):
    pass


class VerificationRequired(WeReadError):
    pass


class QRExpired(WeReadError):
    pass


class QRDeclined(WeReadError):
    pass


class UnsupportedFormat(WeReadError):
    pass


class FileTooLarge(WeReadError):
    pass


class ImportUnconfirmed(WeReadError):
    pass


class ImportParseFailed(WeReadError):
    pass


class ImportLimit(WeReadError):
    pass


class RateLimited(WeReadError):
    pass


class APIError(WeReadError):
    """A WeRead response that carried an error code or an unexpected status."""

    def __init__(self, path: str, status: int, code: int = 0, message: str = "") -> None:
        self.path = path
        self.status = status
        self.code = code
        self.message = message
        super().__init__(self._render())

    def _render(self) -> str:
        if self.code == ERR_CODE_IMPORT_LIMIT:
            base = "WeRead import limit reached"
            return f"{base}: {self.message}" if self.message else base
        if self.code == ERR_CODE_RATE_LIMITED:
            base = "WeRead is limiting requests; try again later"
            return f"{base}: {self.message}" if self.message else base
        text = f"WeRead {self.path} failed (HTTP {self.status}"
        if self.code:
            text += f", errCode {self.code}"
        text += ")"
        if self.message:
            text += ": " + self.message
        return text


class ImportLimitError(APIError, ImportLimit):
    pass


class RateLimitedError(APIError, RateLimited):
    pass


def api_error(path: str, status: int, code: int = 0, message: str = "") -> APIError:
    if code == ERR_CODE_IMPORT_LIMIT:
        return ImportLimitError(path, status, code, message)
    if code == ERR_CODE_RATE_LIMITED:
        return RateLimitedError(path, status, code, message)
    return APIError(path, status, code, message)
