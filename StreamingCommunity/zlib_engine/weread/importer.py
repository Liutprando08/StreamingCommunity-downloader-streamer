"""Import local ebooks into a WeRead shelf.

Mirrors ``internal/weread/import.go``. The sequence is: ask WeRead for a
temporary COS credential, PUT the file to COS, then ask WeRead to add it and
poll until it reports a result. If the final confirmation is lost the book may
already be on the shelf, so the error reads as unconfirmed.
"""

from __future__ import annotations

import os
import re
import threading
import time
import urllib.parse
from dataclasses import dataclass
from enum import IntEnum
from typing import Callable

from ..errors import Cancelled
from .client import Client, cancel_timeout, notify_attempts, notify_interval
from .cos import COS_BUCKET_RE, COSCredentials, UploadCredential, put_cos
from .errors import (
    APIError,
    FileTooLarge,
    ImportParseFailed,
    ImportUnconfirmed,
    NotLoggedIn,
    SessionExpired,
    UnsupportedFormat,
    VerificationRequired,
    WeReadError,
)

IMPORT_FORMATS = (".epub", ".pdf", ".mobi", ".azw3", ".txt")
MAX_TXT_SIZE = 20 << 20
MAX_BOOK_SIZE = 300 << 20

NOTIFY_NONE = -1
NOTIFY_COMPLETED = 0
NOTIFY_PROCESSING = 1
NOTIFY_PARSE_ERROR = 2
NOTIFY_EXISTS = 3

BOOK_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ImportStage(IntEnum):
    PREPARE = 0
    UPLOAD = 1
    PROCESS = 2


@dataclass
class ImportProgress:
    stage: ImportStage
    sent: int = 0
    total: int = 0
    attempt: int = 0
    attempts: int = 0


@dataclass
class ImportResult:
    book_id: str
    name: str
    already_existed: bool = False

    def to_dict(self) -> dict:
        return {
            "book_id": self.book_id,
            "name": self.name,
            "already_existed": self.already_existed,
        }


def max_import_size(path: str) -> int:
    return MAX_TXT_SIZE if os.path.splitext(path)[1].lower() == ".txt" else MAX_BOOK_SIZE


def supported_format(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMPORT_FORMATS


def check_import_file(path: str) -> int:
    """Return the file size or raise why WeRead would refuse it."""
    name = os.path.basename(path)
    if not supported_format(name):
        raise UnsupportedFormat(
            f"WeRead does not accept this file type: {os.path.splitext(name)[1]} "
            f"(accepted: {', '.join(IMPORT_FORMATS)})"
        )
    try:
        info = os.stat(path)
    except OSError:
        raise
    return _check_import_info(name, info)


def _check_import_info(name: str, info: os.stat_result) -> int:
    import stat

    if not stat.S_ISREG(info.st_mode):
        raise WeReadError(f"{name} is not a regular file")
    size = info.st_size
    if size == 0:
        raise WeReadError(f"{name} is empty")
    limit = max_import_size(name)
    if size > limit:
        extension = os.path.splitext(name)[1].lstrip(".").upper()
        raise FileTooLarge(
            f"file is too large for WeRead: {name} is {format_size(size)}; "
            f"the limit for {extension} files is {format_size(limit)}"
        )
    return size


def format_size(size: int) -> str:
    unit = 1024
    if size < unit:
        return f"{size} B"
    value = size / unit
    suffix = "KiB"
    for candidate in ("MiB", "GiB"):
        if value < unit:
            break
        value /= unit
        suffix = candidate
    return f"{value:.1f} {suffix}"


class _ProgressReader:
    def __init__(self, handle, report: Callable[[int], None]) -> None:
        self._handle = handle
        self._report = report
        self.sent = 0

    def read(self, size: int = -1) -> bytes:
        data = self._handle.read(size)
        if data:
            self.sent += len(data)
            self._report(self.sent)
        return data


def upload_credential(client: Client, name: str) -> UploadCredential:
    query = {"name": os.path.splitext(name)[0], "from": ""}
    reply = client._call("GET", "/cos/getcredential", query)
    if not isinstance(reply, dict):
        raise WeReadError("WeRead upload credential response is incomplete")
    bucket = reply.get("bucket")
    object_name = reply.get("ObjectName")
    response = reply.get("Response")
    if not isinstance(response, dict):
        response = {}
    credentials = COSCredentials.from_api(response.get("Credentials"))
    key = object_name.lstrip("/") if isinstance(object_name, str) else ""
    expires = response.get("ExpiredTime")
    try:
        expires = int(expires)
    except (TypeError, ValueError):
        expires = 0
    if (
        not isinstance(bucket, str)
        or not COS_BUCKET_RE.match(bucket)
        or not key
        or ".." in key
        or not credentials.complete()
    ):
        raise WeReadError("WeRead upload credential response is incomplete")
    return UploadCredential(
        bucket=bucket,
        key=key,
        object_name=object_name,
        credentials=credentials,
        expires=expires,
    )


def notify(client: Client, name: str, object_name: str, cancel: bool) -> tuple[int, str]:
    query = {"name": name, "path": object_name, "cancel": "1" if cancel else "0"}
    reply = client._call("POST", "/cos/notify", query, {})
    if not isinstance(reply, dict):
        reply = {}
    status = reply.get("status")
    try:
        status_value = int(status) if status is not None else NOTIFY_NONE
    except (TypeError, ValueError):
        status_value = NOTIFY_NONE
    book_id = reply.get("bookId")
    return status_value, book_id if isinstance(book_id, str) else ""


def import_book(
    client: Client,
    path: str,
    progress: Callable[[ImportProgress], None] | None = None,
    *,
    cancel_event: threading.Event | None = None,
) -> ImportResult:
    def report(value: ImportProgress) -> None:
        if progress is not None:
            progress(value)

    def cancelled() -> bool:
        return cancel_event is not None and cancel_event.is_set()

    name = os.path.basename(path)
    if not supported_format(name):
        raise UnsupportedFormat(
            f"WeRead does not accept this file type: {os.path.splitext(name)[1]} "
            f"(accepted: {', '.join(IMPORT_FORMATS)})"
        )
    if cancelled():
        raise Cancelled("operation cancelled")
    try:
        handle = open(path, "rb")
    except OSError:
        raise
    with handle:
        size = _check_import_info(name, os.fstat(handle.fileno()))

        report(ImportProgress(stage=ImportStage.PREPARE, total=size))
        try:
            credential = upload_credential(client, name)
        except Exception:
            if cancelled():
                raise Cancelled("operation cancelled")
            raise

        report(ImportProgress(stage=ImportStage.UPLOAD, total=size))
        reader = _ProgressReader(
            handle,
            lambda sent: report(ImportProgress(stage=ImportStage.UPLOAD, sent=sent, total=size)),
        )
        try:
            put_cos(client, credential, reader, size, cancel_event=cancel_event)
        except Exception:
            if cancelled():
                raise Cancelled("operation cancelled")
            raise
        if cancelled():
            raise Cancelled("operation cancelled")

        attempt = 1
        while True:
            report(
                ImportProgress(
                    stage=ImportStage.PROCESS,
                    sent=size,
                    total=size,
                    attempt=attempt,
                    attempts=notify_attempts,
                )
            )
            try:
                status, book_id = notify(client, name, credential.object_name, False)
            except Exception as exc:  # noqa: BLE001 - classified below
                if cancelled():
                    raise _abandon(client, name, credential.object_name, Cancelled("operation cancelled")) from exc
                if attempt == 1 and _nothing_added(exc):
                    raise
                raise ImportUnconfirmed(
                    f"WeRead did not confirm the import; check the shelf before retrying: {exc}"
                ) from exc

            if status in {NOTIFY_COMPLETED, NOTIFY_EXISTS}:
                if not BOOK_ID_RE.match(book_id):
                    raise ImportUnconfirmed(
                        "WeRead did not confirm the import; check the shelf before retrying: "
                        "no book ID in the reply"
                    )
                return ImportResult(
                    book_id=book_id,
                    name=name,
                    already_existed=status == NOTIFY_EXISTS,
                )
            if status == NOTIFY_PARSE_ERROR:
                raise ImportParseFailed("WeRead could not read the file as a book")
            if status not in {NOTIFY_PROCESSING, NOTIFY_NONE}:
                error: WeReadError = WeReadError(f"WeRead rejected the import (status {status})")
                if attempt > 1:
                    error = ImportUnconfirmed(
                        f"WeRead did not confirm the import; check the shelf before retrying: {error}"
                    )
                raise error
            if attempt >= notify_attempts:
                raise ImportUnconfirmed(
                    "WeRead did not confirm the import; check the shelf before retrying: "
                    "WeRead was still processing the book"
                )
            if _sleep(notify_interval, cancel_event):
                raise _abandon(client, name, credential.object_name, Cancelled("operation cancelled"))
            attempt += 1


def _nothing_added(exc: BaseException) -> bool:
    if isinstance(exc, (VerificationRequired, SessionExpired, NotLoggedIn)):
        return True
    if isinstance(exc, APIError):
        return exc.status < 500
    return False


def _abandon(client: Client, name: str, object_name: str, cause: BaseException) -> BaseException:
    try:
        notify(client, name, object_name, True)
    except Exception as exc:  # noqa: BLE001 - the import may still finish
        return ImportUnconfirmed(
            "WeRead did not confirm the import; check the shelf before retrying: "
            f"could not cancel the import: {exc}"
        )
    return cause


def _sleep(seconds: float, cancel_event: threading.Event | None) -> bool:
    """Sleep; return True when cancellation interrupted the wait."""
    if cancel_event is None:
        time.sleep(seconds)
        return False
    return cancel_event.wait(seconds)


__all__ = [
    "IMPORT_FORMATS",
    "ImportStage",
    "ImportProgress",
    "ImportResult",
    "max_import_size",
    "supported_format",
    "check_import_file",
    "import_book",
    "format_size",
    "upload_credential",
    "notify",
]


# api_timeout/cancel_timeout re-exported for callers that shorten notifications.
_ = (urllib.parse, cancel_timeout)
