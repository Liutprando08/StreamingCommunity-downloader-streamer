# 19.11.26 - Z-Library book downloader.
#
# The engine streams the file itself (atomic temp file + rename), so this
# module only resolves the destination, bridges progress into the shared
# ``download_tracker`` and translates engine errors into queue-friendly
# results. It returns the downloaded path, or ``None`` on any failure, which
# is exactly what ``QueueScreen`` expects from an atomic provider.

from __future__ import annotations

import logging
import os
import time

# Engine
from StreamingCommunity.zlib_engine import (
    Cancelled,
    DownloadFailed,
    NotLoggedIn,
    SessionExpired,
    ZlibError,
)

# Internal utilities
from StreamingCommunity.services._base import site_constants
from StreamingCommunity.services._base.music_downloader import human_size
from StreamingCommunity.source.utils.tracker import context_tracker, download_tracker
from StreamingCommunity.utils import os_manager
from StreamingCommunity.utils.console.shared import console

# Logic
from . import client as zclient
from .mapper import split_book_key

logger = logging.getLogger(__name__)

TASK_KEY = "book"


class BookDownloadReporter:
    """Bridge engine progress callbacks into ``download_tracker``.

    The engine never touches the tracker, so the TUI queue/activity screens
    would stay at 0% without this. When no GUI context is active the reporter
    is inert.
    """

    def __init__(self, entry) -> None:
        self.download_id = getattr(context_tracker, "download_id", None)
        self._started = time.monotonic()
        self._last_percent = -1

    def progress(self, received: int, total: int) -> None:
        if not self.download_id:
            return

        percent = 0.0 if total <= 0 else min(100.0, received * 100.0 / total)
        # ``update_progress`` takes a lock on every call; the queue redraws
        # twice a second, so skip the sub-percent noise.
        if total > 0 and int(percent) == self._last_percent:
            return
        self._last_percent = int(percent)

        elapsed = max(time.monotonic() - self._started, 0.001)
        speed = f"{human_size(int(received / elapsed))}/s" if received else "0B/s"
        size = (
            f"{human_size(received)}/{human_size(total)}"
            if total
            else human_size(received)
        )
        try:
            download_tracker.update_progress(
                self.download_id, TASK_KEY, percent, speed, size
            )
        except Exception:  # pragma: no cover - tracker must never break a download
            logger.debug("zlibrary: tracker progress update failed", exc_info=True)

    def complete(
        self, success: bool = True, path: str | None = None, error: str | None = None
    ) -> None:
        if not self.download_id:
            return
        try:
            download_tracker.complete_download(
                self.download_id, success=success, path=path, error=error
            )
        except Exception:  # pragma: no cover - tracker must never break a download
            logger.debug("zlibrary: tracker completion failed", exc_info=True)


def book_output_dir(entry) -> str:
    """Return ``<root>/Books/<first author>/``, creating it if needed."""
    authors = str(getattr(entry, "authors", "") or "")
    first_author = authors.split(",")[0].strip()

    author_folder = (
        os_manager.get_sanitize_file(first_author) if first_author else "Unknown"
    )
    folder = os.path.join(site_constants.BOOK_FOLDER, author_folder or "Unknown")
    os_manager.create_path(folder)
    return folder


def book_download_url(entry, domain: str) -> str:
    """Rebuild the EAPI file endpoint from the ``<id>:<hash>`` handle."""
    book_id, book_hash = split_book_key(getattr(entry, "id", ""))
    if not (book_id and book_hash):
        raise DownloadFailed(
            "zlibrary: entry has no usable id/hash (search again to refresh it)"
        )
    return f"{domain.rstrip('/')}/eapi/book/{book_id}/{book_hash}/file"


def _run(client, entry, folder: str, reporter: BookDownloadReporter, cancel_event):
    url = book_download_url(entry, client.domain)
    return client.download(
        url, folder, progress=reporter.progress, cancel_event=cancel_event
    )


def download_book(entry) -> str | None:
    """Download one book and return its path, or ``None`` on failure."""
    reporter = BookDownloadReporter(entry)
    cancel_event = (
        download_tracker.stop_events.get(reporter.download_id)
        if reporter.download_id
        else None
    )

    try:
        client = zclient.get_client()
    except NotLoggedIn as error:
        console.print(f"\n[red]{error}")
        console.print(
            "[dim]Suggerimento: incolla i cookie remix_userid/remix_userkey "
            "in Conf/login.json se il login con password fallisce.[/]"
        )
        reporter.complete(False, error=str(error))
        return None
    except ZlibError as error:
        console.print(f"\n[red]Z-Library: {error}")
        reporter.complete(False, error=str(error))
        return None

    folder = book_output_dir(entry)
    name = str(getattr(entry, "name", "") or "libro")
    console.print(f"\n[cyan]Download libro: [magenta]{name}[/] → [green]{folder}")

    try:
        result = zclient.run_with_mirror_retry(
            lambda active: _run(active, entry, folder, reporter, cancel_event)
        )
    except SessionExpired:
        # Cookies expired: one silent password re-login, then a single retry.
        try:
            zclient.relogin(client)
            result = zclient.run_with_mirror_retry(
                lambda active: _run(active, entry, folder, reporter, cancel_event)
            )
        except Cancelled:
            console.print("[yellow]Download annullato.")
            reporter.complete(False, error="cancelled")
            return None
        except ZlibError as error:
            console.print(f"\n[red]Z-Library: {error}")
            reporter.complete(False, error=str(error))
            return None
        except OSError as error:
            logger.debug("zlibrary: download I/O failure", exc_info=True)
            console.print(f"\n[red]Z-Library: errore di scrittura: {error}")
            reporter.complete(False, error=str(error))
            return None
    except Cancelled:
        console.print("[yellow]Download annullato.")
        reporter.complete(False, error="cancelled")
        return None
    except ZlibError as error:
        console.print(f"\n[red]Z-Library: {error}")
        reporter.complete(False, error=str(error))
        return None
    except OSError as error:
        logger.debug("zlibrary: download I/O failure", exc_info=True)
        console.print(f"\n[red]Z-Library: errore di scrittura: {error}")
        reporter.complete(False, error=str(error))
        return None

    path = result.file_path
    reporter.complete(True, path=path)
    console.print(f"[green]Salvato:[/] {path} ({human_size(result.size)})")
    return path


__all__ = ["download_book", "book_output_dir", "book_download_url", "BookDownloadReporter"]
