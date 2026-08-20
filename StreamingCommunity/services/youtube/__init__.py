from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional
import yt_dlp

from rich.console import Console
from yt_dlp.utils import ExtractorError
from StreamingCommunity.services._base import Entries, EntriesManager
from StreamingCommunity.services._base.site_search_manager import (
    base_process_search_result,
    base_search,
)
from StreamingCommunity.utils import TVShowManager

logger = logging.getLogger(__name__)
console = Console()
entries_manager = EntriesManager()
table_show_manager = TVShowManager()
_useFor = "Film_Serie"
search_url = "youtube.com"


def title_search(query: str) -> int:
    entries_manager.clear()
    table_show_manager.clear()
    try:
        console.print(f"[cyan]Searching: [yellow]{search_url}")
        infos = yt_dlp.YoutubeDL({"quiet": True, "extract_flat": True}).extract_info(
            f"ytsearch20:{query}", download=False
        )
    except ExtractorError as e:
        logger.error(f"request search error: {e}")
    if not infos:
        console.print("[yellow]No result found on this page")
    return 1


def search(
    title_search_func: Callable[[str], int],
    process_result_func: Callable[
        [Entries | None, dict[str, str] | None, Any | None], bool
    ],
    media_search_manager: EntriesManager,
    table_show_manager: TVShowManager,
    site_name: str,
    string_to_search: str | None = None,
    get_onlyDatabase: bool = False,
    direct_item: dict[str, Any] | None = None,
    selections: dict[str, str] | None = None,
    scrape_serie: Any | None = None,
) -> Any:
    return base_search(
        title_search_func=title_search,
        process_result_func=process_search_result,
        media_search_manager=entries_manager,
        table_show_manager=table_show_manager,
        site_name=site_constants.SITE_NAME,
        string_to_search=string_to_search,
        get_onlyDatabase=get_onlyDatabase,
        direct_item=direct_item,
        selections=selections,
        scrape_serie=scrape_serie,
    )
