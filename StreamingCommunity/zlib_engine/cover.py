"""Cover fetching with dimension limits and a small disk cache.

The Go engine decodes covers with ``image.Decode``. The Python port stays
stdlib-only, so it sniffs PNG, JPEG and GIF headers and validates the declared
dimensions before returning the bytes. No account cookies or EAPI headers are
sent: cover URLs are untrusted input.
"""

from __future__ import annotations

import hashlib
import os
import struct
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .client import Client, _NoRedirect, check_cancelled
from .errors import ZlibError

COVER_CACHE_MAX_FILES = 300
COVER_CACHE_MAX_BYTES = 96 << 20
COVER_MAX_BYTES = 2 << 20
COVER_MAX_REDIRECTS = 5
COVER_TIMEOUT = 6.0


@dataclass
class Cover:
    data: bytes
    width: int
    height: int
    format: str

    @property
    def content_type(self) -> str:
        return {
            "png": "image/png",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
        }[self.format]


def _dimensions(data: bytes) -> tuple[str, int, int]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return "png", width, height
    if data[:6] in {b"GIF87a", b"GIF89a"} and len(data) >= 10:
        width, height = struct.unpack("<HH", data[6:10])
        return "gif", width, height
    if data.startswith(b"\xff\xd8"):
        width, height = _jpeg_dimensions(data)
        return "jpeg", width, height
    raise ZlibError("unsupported cover format")


def _jpeg_dimensions(data: bytes) -> tuple[int, int]:
    index = 2
    length = len(data)
    sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while index + 1 < length:
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in {0xD8, 0xD9, 0x01} or 0xD0 <= marker <= 0xD7:
            continue
        if index + 2 > length:
            break
        segment_length = struct.unpack(">H", data[index : index + 2])[0]
        if marker in sof_markers and index + 7 <= length:
            height, width = struct.unpack(">HH", data[index + 3 : index + 7])
            return width, height
        if segment_length < 2:
            break
        index += segment_length
    raise ZlibError("unsupported cover dimensions")


def decode_cover(data: bytes) -> Cover:
    """Validate a cover's declared dimensions before accepting its bytes."""
    fmt, width, height = _dimensions(data)
    if (
        width <= 0
        or height <= 0
        or width > 4096
        or height > 4096
        or width * height > 4_000_000
    ):
        raise ZlibError("unsupported cover dimensions")
    return Cover(data=data, width=width, height=height, format=fmt)


def fetch_cover(
    client: Client, raw_url: str, *, cancel_event: threading.Event | None = None
) -> Cover:
    check_cancelled(cancel_event)
    try:
        base = urllib.parse.urlsplit(client.domain)
        target = urllib.parse.urlsplit(urllib.parse.urljoin(client.domain + "/", raw_url))
    except ValueError as exc:
        raise ZlibError("invalid cover URL") from exc
    if not raw_url or not base.hostname:
        raise ZlibError("invalid cover origin")
    _validate_cover_url(target)

    cached = _read_cache(client, target.geturl())
    if cached is not None:
        return cached

    opener = _cover_opener(client)
    url = target.geturl()
    response = None
    for redirects in range(COVER_MAX_REDIRECTS + 1):
        check_cancelled(cancel_event)
        request = urllib.request.Request(url, headers={"User-Agent": "zlib-engine"})
        try:
            response = opener.open(request, timeout=COVER_TIMEOUT)
        except urllib.error.HTTPError as exc:
            response = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ZlibError("cover unavailable") from exc
        status = int(getattr(response, "status", None) or getattr(response, "code", 0) or 0)
        location = response.headers.get("Location") if response.headers else None
        if status in {301, 302, 303, 307, 308} and location:
            response.close()
            if redirects >= COVER_MAX_REDIRECTS:
                raise ZlibError("too many cover redirects")
            next_url = urllib.parse.urljoin(url, location)
            _validate_cover_url(urllib.parse.urlsplit(next_url))
            url = next_url
            continue
        try:
            if status != 200:
                raise ZlibError("cover unavailable")
            payload = response.read(COVER_MAX_BYTES + 1)
        finally:
            response.close()
        if len(payload) > COVER_MAX_BYTES:
            raise ZlibError("cover exceeds size limit")
        cover = decode_cover(payload)
        _write_cache(client, url, payload)
        return cover
    raise ZlibError("too many cover redirects")


def _validate_cover_url(target: urllib.parse.SplitResult) -> None:
    if (
        target.scheme != "https"
        or not target.hostname
        or target.username is not None
        or target.password is not None
        or target.port is not None
    ):
        raise ZlibError("invalid cover URL")


def _cover_opener(client: Client) -> urllib.request.OpenerDirector:
    handlers: list = [_NoRedirect()]
    proxy = getattr(client, "_proxy_value", "")
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        handlers.append(urllib.request.ProxyHandler())
    return urllib.request.build_opener(*handlers)


def _cache_path(client: Client, raw_url: str) -> str:
    digest = hashlib.sha256(raw_url.encode("utf-8")).hexdigest()
    return os.path.join(client._cover_cache_dir, digest + ".img")


def _read_cache(client: Client, raw_url: str) -> Cover | None:
    directory = client._cover_cache_dir
    if not directory:
        return None
    path = _cache_path(client, raw_url)
    try:
        with open(path, "rb") as handle:
            data = handle.read(COVER_MAX_BYTES + 1)
    except OSError:
        return None
    if len(data) > COVER_MAX_BYTES:
        return None
    try:
        cover = decode_cover(data)
    except ZlibError:
        try:
            os.unlink(path)
        except OSError:
            pass
        return None
    try:
        now = time.time()
        os.utime(path, (now, now))
    except OSError:
        pass
    return cover


def _write_cache(client: Client, raw_url: str, data: bytes) -> None:
    directory = client._cover_cache_dir
    if not directory:
        return
    try:
        os.makedirs(directory, mode=0o700, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".cover-", suffix=".part", dir=directory)
    except OSError:
        return
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp_path, _cache_path(client, raw_url))
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return
    _prune_cache(directory)


def _prune_cache(directory: str) -> None:
    try:
        entries = list(os.scandir(directory))
    except OSError:
        return
    files: list[tuple[str, int, float]] = []
    total = 0
    for entry in entries:
        try:
            info = entry.stat()
        except OSError:
            continue
        if not entry.is_file() or not entry.name.endswith(".img"):
            continue
        files.append((entry.path, info.st_size, info.st_mtime))
        total += info.st_size
    if len(files) <= COVER_CACHE_MAX_FILES and total <= COVER_CACHE_MAX_BYTES:
        return
    files.sort(key=lambda item: item[2])
    remaining = len(files)
    for path, size, _ in files:
        if remaining <= COVER_CACHE_MAX_FILES and total <= COVER_CACHE_MAX_BYTES:
            break
        try:
            os.unlink(path)
        except OSError:
            continue
        total -= size
        remaining -= 1


__all__ = ["Cover", "decode_cover", "fetch_cover", "COVER_MAX_BYTES"]
