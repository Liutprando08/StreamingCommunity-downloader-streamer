"""WeRead (微信读书) import client.

WeRead publishes no upload API. This package identifies as the WeRead e-ink
app and uses the same credential → Tencent COS → notify sequence. The
endpoints are unofficial and may change without notice.
"""

from .client import Client, Credentials
from .errors import (
    APIError,
    FileTooLarge,
    ImportLimit,
    ImportParseFailed,
    ImportUnconfirmed,
    NotLoggedIn,
    QRDeclined,
    QRExpired,
    RateLimited,
    SessionExpired,
    UnsupportedFormat,
    VerificationRequired,
    WeReadError,
)
from .importer import (
    IMPORT_FORMATS,
    ImportProgress,
    ImportResult,
    ImportStage,
    check_import_file,
    import_book,
    max_import_size,
    supported_format,
)
from .login import QRCode

__all__ = [
    "Client",
    "Credentials",
    "QRCode",
    "WeReadError",
    "APIError",
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
    "IMPORT_FORMATS",
    "ImportStage",
    "ImportProgress",
    "ImportResult",
    "check_import_file",
    "import_book",
    "max_import_size",
    "supported_format",
]
