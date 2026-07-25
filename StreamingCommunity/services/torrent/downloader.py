# 2026

import os
import shutil
import logging
from typing import Optional


# External library
from rich.console import Console


# Internal utilities
from StreamingCommunity.services._base.site_costant import site_constants
from StreamingCommunity.setup import get_aria2c_path
from StreamingCommunity.torrent.downloader import TorrentDownloader


# Variable
console = Console()
log = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm", ".ts", ".m4v"}

MIN_SPACE_BYTES = 500 * 1024 * 1024  # 500 MB minimum free space


def _get_downloader(is_movie: bool = True) -> Optional[TorrentDownloader]:
    """Create a TorrentDownloader with the correct output path."""
    aria2c = get_aria2c_path()
    if not aria2c:
        console.print("[red]aria2c not found. Cannot download torrent.")
        return None

    if is_movie:
        download_path = site_constants.MOVIE_FOLDER
    else:
        download_path = site_constants.SERIES_FOLDER

    os.makedirs(download_path, exist_ok=True)
    return TorrentDownloader(aria2c, download_path)


def _check_disk_space(path: str, min_bytes: int = MIN_SPACE_BYTES) -> bool:
    """Check if there is enough disk space. Returns True if OK."""
    try:
        usage = shutil.disk_usage(path)
        free_gb = usage.free / (1024 ** 3)
        if usage.free < min_bytes:
            min_gb = min_bytes / (1024 ** 3)
            console.print(f"[red]Insufficient disk space: {free_gb:.1f} GB free, {min_gb:.1f} GB required")
            return False
        log.info("Disk space check OK: %.1f GB free", free_gb)
        return True
    except Exception as e:
        log.warning("Disk space check failed: %s", e)
        return True


def _snapshot_files(download_dir: str) -> set:
    """Snapshot all file paths in a directory tree."""
    snapshot = set()
    if not os.path.isdir(download_dir):
        return snapshot
    for root, _dirs, files in os.walk(download_dir):
        for f in files:
            snapshot.add(os.path.join(root, f))
    return snapshot


def _find_new_video(before: set, download_dir: str) -> Optional[str]:
    """Find the newest video file by creation time that wasn't present in the before snapshot."""
    candidates = []
    for root, _dirs, files in os.walk(download_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in VIDEO_EXTENSIONS:
                full_path = os.path.join(root, f)
                if full_path not in before:
                    candidates.append(full_path)

    if not candidates:
        return None

    candidates.sort(key=lambda p: os.path.getctime(p))
    return candidates[0]


def _find_video_file(download_dir: str) -> Optional[str]:
    """Fallback: find the largest video file in the download directory."""
    if not os.path.isdir(download_dir):
        return None

    candidates = []
    for root, _dirs, files in os.walk(download_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in VIDEO_EXTENSIONS:
                full_path = os.path.join(root, f)
                candidates.append(full_path)

    if not candidates:
        return None

    candidates.sort(key=lambda p: os.path.getsize(p), reverse=True)
    return candidates[0]


def _download_impl(select_title, is_movie: bool) -> Optional[str]:
    """Common download logic for both films and series."""
    from StreamingCommunity.services.torrent import _torrent_results

    torrent = _torrent_results.get(select_title.id)
    if not torrent or not torrent.magnet_url:
        console.print("[red]No torrent data found for selected item.")
        return None

    downloader = _get_downloader(is_movie=is_movie)
    if not downloader:
        return None

    if not _check_disk_space(downloader.download_path):
        return None

    console.print(f"[cyan]Downloading: [yellow]{select_title.name}")
    console.print(f"[cyan]Source: [yellow]{torrent.source} [cyan]| Quality: [yellow]{torrent.quality}")

    before = _snapshot_files(downloader.download_path)
    result = downloader.download_magnet(torrent.magnet_url)

    if result:
        console.print(f"[green]Download completed: {result}")

        video_file = _find_new_video(before, result) or _find_video_file(result)
        if video_file:
            from StreamingCommunity.services.torrent.audio_dub import prompt_audio_dub
            dubbed = prompt_audio_dub(select_title, video_file)
            if dubbed:
                console.print(f"[green]Dubbed version: {dubbed}")
    else:
        console.print("[red]Download failed or timed out.")

    return result


def download_film(select_title) -> Optional[str]:
    """Download a torrent for a film."""
    return _download_impl(select_title, is_movie=True)


def download_series(
    select_title,
    season_selection: Optional[str] = None,
    episode_selection: Optional[str] = None,
    scrape_serie=None,
) -> Optional[str]:
    """Download a torrent for a series."""
    return _download_impl(select_title, is_movie=False)
