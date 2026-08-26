# 2026

import logging
import threading
from typing import Dict, Optional


# External library
from rich.prompt import Prompt


# Internal utilities
from StreamingCommunity.utils import TVShowManager, config_manager
from StreamingCommunity.utils.console.shared import console
from StreamingCommunity.services._base import EntriesManager, Entries
from StreamingCommunity.services._base.site_search_manager import base_process_search_result, base_search
from StreamingCommunity.torrent.title_parser import TorrentResult
from StreamingCommunity.torrent.searcher import Searcher


# Logic
from .downloader import download_film, download_series


# Variable
_useFor = "Film_Serie"

msg = Prompt()
entries_manager = EntriesManager()
table_show_manager = TVShowManager()

_torrent_results: Dict[int, TorrentResult] = {}
_torrent_lock = threading.Lock()


def _format_size(size_bytes: int) -> str:
    """Convert bytes to human-readable size string."""
    if size_bytes <= 0:
        return "N/A"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size_bytes)
    for unit in units:
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def title_search(query: str) -> int:
    """Search all torrent scrapers and populate entries_manager."""
    entries_manager.clear()
    table_show_manager.clear()
    with _torrent_lock:
        _torrent_results.clear()

    searcher = Searcher(config_manager)

    if not searcher.is_enabled():
        console.print("[yellow]Torrent search is disabled in config")
        return 0

    results = searcher.search_all(query)

    with _torrent_lock:
        for i, r in enumerate(results):
            _torrent_results[i] = r

            media_type = "film" if r.category in ("movie", "movies") else "tv"

            entries_manager.add(Entries(
                id=i,
                name=r.title,
                type=media_type,
                quality=r.quality or "N/A",
                size=_format_size(r.size_bytes),
                seeders=r.seeders,
                source=r.source,
                year=str(r.year) if r.year else "9999",
            ))

    return len(results)


def process_search_result(select_title, selections=None, scrape_serie=None):
    return base_process_search_result(
        select_title=select_title,
        download_film_func=download_film,
        download_series_func=download_series,
        media_search_manager=entries_manager,
        table_show_manager=table_show_manager,
        selections=selections,
        scrape_serie=scrape_serie,
    )


def search(
    string_to_search: Optional[str] = None,
    get_onlyDatabase: bool = False,
    direct_item: Optional[dict] = None,
    selections: Optional[dict] = None,
    scrape_serie=None,
):
    return base_search(
        title_search_func=title_search,
        process_result_func=process_search_result,
        media_search_manager=entries_manager,
        table_show_manager=table_show_manager,
        site_name="torrent",
        string_to_search=string_to_search,
        get_onlyDatabase=get_onlyDatabase,
        direct_item=direct_item,
        selections=selections,
        scrape_serie=scrape_serie,
    )
