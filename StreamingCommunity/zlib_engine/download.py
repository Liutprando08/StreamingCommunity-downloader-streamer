"""Streaming downloads with retries, stall detection and atomic renames.

Mirrors ``internal/zlib/download.go``. A partial download is written to a
temporary file beside the destination and renamed only after the whole body
was read, so a failure never truncates an existing book.
"""

from __future__ import annotations

import os
import posixpath
import re
import tempfile
import threading
import time
import urllib.parse
from email.message import Message
from typing import Callable

from .client import Client, check_cancelled, is_retryable_status
from .constants import DEFAULT_USER_AGENT
from .errors import Cancelled, DownloadFailed, TransportError
from .model import DownloadResult
from .text import is_bidi_control, strip_control

DEFAULT_DOWNLOAD_RETRIES = 3
DEFAULT_STALL_TIMEOUT = 120.0

# Vars so tests can shorten them, matching the Go package vars.
download_retry_base = 1.0
download_stall_timeout = DEFAULT_STALL_TIMEOUT

_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *{f"COM{index}" for index in range(1, 10)},
    *{f"LPT{index}" for index in range(1, 10)},
}


def resolve_download_retries(raw: str | None) -> int:
    if raw is None:
        return DEFAULT_DOWNLOAD_RETRIES
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        return DEFAULT_DOWNLOAD_RETRIES
    if value < 0:
        return DEFAULT_DOWNLOAD_RETRIES
    return value


def download(
    client: Client,
    download_url: str,
    dest_dir: str,
    progress: Callable[[int, int], None] | None = None,
    *,
    cancel_event: threading.Event | None = None,
) -> DownloadResult:
    check_cancelled(cancel_event)
    from .eapi import resolve_eapi_file_url

    resolved = resolve_eapi_file_url(client, download_url)
    check_cancelled(cancel_event)
    os.makedirs(dest_dir, exist_ok=True)

    def report(written: int, total: int) -> None:
        check_cancelled(cancel_event)
        if progress is not None:
            progress(written, total)

    response = _open_download(client, resolved, cancel_event)
    try:
        status = int(response.status or 0)
        if status != 200:
            raise DownloadFailed(f"zlibrary: download failed: HTTP {status}")
        filename = sanitize_filename(filename_from_response(response.headers, resolved))
        dest_path = os.path.join(dest_dir, filename)
        written = _save(response, dest_path, report, cancel_event)
        return DownloadResult(file_path=dest_path, size=written)
    finally:
        response.close()


def _open_download(client: Client, raw_url: str, cancel_event: threading.Event | None):
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": client.domain + "/",
        "Accept-Encoding": "identity",
    }
    if _sends_credentials(client, raw_url):
        cookies = client.cookies()
        if cookies:
            headers["Cookie"] = "; ".join(f"{name}={value}" for name, value in cookies.items())

    last_error: BaseException | None = None
    delay = download_retry_base
    attempts = max(client._download_retries, 0)
    for attempt in range(attempts + 1):
        if attempt:
            _sleep(delay, cancel_event)
            delay *= 2
        check_cancelled(cancel_event)
        try:
            status, _headers, response, _url = client._open_stream(
                "GET", raw_url, None, headers, timeout=download_stall_timeout
            )
        except TransportError as exc:
            last_error = exc
            continue
        if is_retryable_status(int(status or 0)):
            last_error = DownloadFailed(f"zlibrary: download failed: HTTP {status}")
            _drain(response)
            continue
        return response
    assert last_error is not None
    raise last_error


def _sends_credentials(client: Client, raw_url: str) -> bool:
    try:
        target = urllib.parse.urlsplit(raw_url)
        base = urllib.parse.urlsplit(client.domain)
    except ValueError:
        return False
    return target.scheme == base.scheme and target.netloc.lower() == base.netloc.lower()


def _drain(response) -> None:
    try:
        response.read(64 * 1024)
    except (OSError, ValueError):
        pass
    finally:
        response.close()


def _sleep(seconds: float, cancel_event: threading.Event | None) -> None:
    deadline = time.monotonic() + seconds
    while True:
        check_cancelled(cancel_event)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        if cancel_event is not None:
            cancel_event.wait(min(remaining, 0.1))
        else:
            time.sleep(min(remaining, 0.1))


def _save(
    response,
    dest_path: str,
    progress: Callable[[int, int], None],
    cancel_event: threading.Event | None,
) -> int:
    directory = os.path.dirname(dest_path) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".zlib-", suffix=".part", dir=directory)
    committed = False
    try:
        total = _content_length(response.headers)
        written = 0
        with os.fdopen(fd, "wb") as handle:
            while True:
                check_cancelled(cancel_event)
                try:
                    chunk = response.read(32 * 1024)
                except (TimeoutError, OSError) as exc:
                    raise DownloadFailed(
                        f"zlibrary: download failed: no data received for {download_stall_timeout:g} seconds"
                    ) from exc
                if not chunk:
                    break
                handle.write(chunk)
                written += len(chunk)
                progress(written, total)
            handle.flush()
            os.fsync(handle.fileno())
            os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, dest_path)
        committed = True
        return written
    finally:
        if not committed:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _content_length(headers) -> int:
    if headers is None:
        return -1
    value = headers.get("Content-Length")
    if value is None:
        return -1
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def filename_from_response(headers, fallback_url: str) -> str:
    if headers is not None:
        disposition = headers.get("Content-Disposition", "")
        if disposition:
            for part in disposition.split(";"):
                part = part.strip()
                if part.startswith("filename="):
                    name = part[len("filename=") :].strip().strip("\"'")
                    if name:
                        return clean_filename(name)
    path = urllib.parse.urlsplit(fallback_url).path
    name = path.rsplit("/", 1)[-1] if path else ""
    return name or "download"


def sanitize_filename(name: str, goos: str | None = None) -> str:
    """Make a server-controlled filename safe to write and print."""
    name = (name or "").replace("\\", "/")
    name = "".join(char for char in name if not is_bidi_control(char))
    name = strip_control(posixpath.basename(name), "")
    if goos is None:
        goos = "windows" if os.name == "nt" else "linux"
    if goos == "windows":
        name = _windows_filename(name)
    if name in {"", ".", "..", "/"}:
        return "download"
    return name


def _windows_filename(name: str) -> str:
    name = re.sub(r'[<>:"|?*]', "_", name)
    name = name.rstrip(". ")
    stem = name.split(".", 1)[0]
    if stem.strip().upper() in _WINDOWS_RESERVED:
        name = "_" + name
    return name


def clean_filename(name: str) -> str:
    """Drop a trailing ``(z-library.sk, ...)`` domain group from a filename."""
    stem, extension = posixpath.splitext(name)
    index = stem.rfind(" (")
    if index >= 0:
        tail = stem[index + 2 :]
        if tail.endswith(")") and "z-lib" in tail:
            stem = stem[:index]
    stem = stem.strip()
    if not stem:
        return name
    return stem + extension


__all__ = [
    "download",
    "sanitize_filename",
    "clean_filename",
    "filename_from_response",
    "resolve_download_retries",
    "DEFAULT_DOWNLOAD_RETRIES",
]


# Message is imported for isinstance checks in callers that pass email headers.
_ = (Message, Cancelled)
