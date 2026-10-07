# 28.08.26

from __future__ import annotations

import os

# Internal utilities
from StreamingCommunity.services._base import Entries, site_constants
from StreamingCommunity.source.utils.tracker import context_tracker, download_tracker
from StreamingCommunity.utils import os_manager
from StreamingCommunity.utils.console.shared import console


def human_size(size: int) -> str:
    """Format a byte count as a short human-readable string."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


class TrackDownloadReporter:
    """Report track download progress to the shared ``download_tracker``.

    The TUI polls that tracker to fill its queue table, but the music services
    stream raw audio over httpx instead of going through the N_m3u8 wrapper that
    normally registers the download. This bridges the two, and stays inert
    (no-op) when the CLI runs without a GUI context.
    """

    def __init__(self, entry: Entries):
        self.entry = entry
        self.download_id = getattr(context_tracker, "download_id", None)
        self.total = 0
        self._last_percent = -1

    def start(self) -> None:
        if not self.download_id:
            return
        download_tracker.start_download(
            self.download_id,
            str(getattr(self.entry, "name", "") or "track"),
            site=str(getattr(context_tracker, "site_name", "") or "music"),
            media_type=str(getattr(context_tracker, "media_type", "") or "Track"),
        )
        download_tracker.update_status(self.download_id, "downloading")

    def progress(self, downloaded: int, total: int) -> None:
        if not self.download_id:
            return

        self.total = total
        percent = 0.0 if total <= 0 else min(100.0, downloaded * 100.0 / total)
        # update_progress takes a lock on every call; the queue only redraws
        # twice a second, so skip the sub-percent noise.
        if total > 0 and int(percent) == self._last_percent:
            return
        self._last_percent = int(percent)

        speed = f"{human_size(downloaded / 5)}/s" if downloaded else "0B/s"
        size = f"{human_size(downloaded)}/{human_size(total)}" if total else human_size(downloaded)
        download_tracker.update_progress(
            self.download_id, "audio", percent, speed, size
        )

    def complete(self, success: bool = True, path: str | None = None, error: str | None = None) -> None:
        if not self.download_id:
            return
        download_tracker.complete_download(
            self.download_id, success=success, path=path, error=error
        )


def music_filename(entry: Entries) -> str:
    """
    Build a sanitized .mp3 filename for a track entry.
    """
    artist = str(getattr(entry, "artist", "") or getattr(entry, "album_artist", "") or "Unknown")
    name = str(getattr(entry, "name", "") or "track")
    return f"{os_manager.get_sanitize_file(artist)} - {os_manager.get_sanitize_file(name)}.mp3"


def music_output_path(entry: Entries) -> str:
    """
    Build the output folder based on artist / album metadata.
    """
    base = site_constants.MUSIC_FOLDER
    artist = str(getattr(entry, "artist", "") or getattr(entry, "album_artist", "") or "Unknown")
    album = str(getattr(entry, "album", "") or "Single")

    folder = os.path.join(base, os_manager.get_sanitize_file(artist))
    if album and album.lower() != "single":
        folder = os.path.join(folder, os_manager.get_sanitize_file(album))

    os_manager.create_path(folder)
    return os.path.join(folder, music_filename(entry))
