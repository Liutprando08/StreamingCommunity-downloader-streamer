# 2026

import os
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


def download_film(select_title) -> Optional[str]:
    """
    Download a torrent for a film.

    Parameters:
        select_title: The selected Entries object with torrent metadata.

    Returns:
        str: Download path on success, None on failure.
    """
    from StreamingCommunity.services.torrent import _torrent_results

    torrent = _torrent_results.get(select_title.id)
    if not torrent or not torrent.magnet_url:
        console.print("[red]No torrent data found for selected item.")
        return None

    downloader = _get_downloader(is_movie=True)
    if not downloader:
        return None

    console.print(f"[cyan]Downloading: [yellow]{select_title.name}")
    console.print(f"[cyan]Source: [yellow]{torrent.source} [cyan]| Quality: [yellow]{torrent.quality}")

    result = downloader.download_magnet(torrent.magnet_url)

    if result:
        console.print(f"[green]Download completed: {result}")
    else:
        console.print("[red]Download failed or timed out.")

    return result


def download_series(
    select_title,
    season_selection: Optional[str] = None,
    episode_selection: Optional[str] = None,
    scrape_serie=None,
) -> Optional[str]:
    """
    Download a torrent for a series.

    Parameters:
        select_title: The selected Entries object with torrent metadata.
        season_selection: Not used for torrent (whole pack download).
        episode_selection: Not used for torrent (whole pack download).
        scrape_serie: Not used for torrent.

    Returns:
        str: Download path on success, None on failure.
    """
    from StreamingCommunity.services.torrent import _torrent_results

    torrent = _torrent_results.get(select_title.id)
    if not torrent or not torrent.magnet_url:
        console.print("[red]No torrent data found for selected item.")
        return None

    downloader = _get_downloader(is_movie=False)
    if not downloader:
        return None

    console.print(f"[cyan]Downloading: [yellow]{select_title.name}")
    console.print(f"[cyan]Source: [yellow]{torrent.source} [cyan]| Quality: [yellow]{torrent.quality}")

    result = downloader.download_magnet(torrent.magnet_url)

    if result:
        console.print(f"[green]Download completed: {result}")
    else:
        console.print("[red]Download failed or timed out.")

    return result
