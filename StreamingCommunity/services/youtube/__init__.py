# 21.08.26
from __future__ import annotations

from typing import Any

import yt_dlp
from rich.prompt import Prompt
from yt_dlp.utils import DownloadError, ExtractorError

from StreamingCommunity.services._base import Entries, EntriesManager, site_constants
from StreamingCommunity.services._base.site_search_manager import (
    base_process_search_result,
    base_search,
)

# Internal utilities
from StreamingCommunity.utils import TVShowManager
from StreamingCommunity.utils.console.shared import console

# Logic
from .downloader import download_film

# Variables
indice = 19
_useFor = "Film_Serie"
search_url = "youtube.com"
msg = Prompt()
entries_manager = EntriesManager()
table_show_manager = TVShowManager()


def _format_duration(seconds) -> str:
    """Format a duration in seconds as H:MM:SS or M:SS."""
    if not seconds:
        return ""
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return ""

    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def title_search(query: str) -> int:
    """
    Search for videos on YouTube using yt-dlp.

    Parameters:
        query (str): Search query

    Returns:
        int: Number of results found
    """
    entries_manager.clear()
    table_show_manager.clear()

    console.print(f"[cyan]Search url: [yellow]{search_url}")

    try:
        ydl_opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[reportArgumentType]
            infos = ydl.extract_info(f"ytsearch20:{query}", download=False)
    except (ExtractorError, DownloadError) as e:
        console.print(
            f"[red]Site: {site_constants.SITE_NAME}, request search error: {e}"
        )
        return 0

    if not infos:
        console.print("[yellow]No result found on this page")
        return 0

    for dict_title in infos.get("entries") or []:
        try:
            if not dict_title or not dict_title.get("id"):
                continue

            video_id = dict_title.get("id")
            entries_manager.add(
                Entries(
                    id=video_id,
                    name=dict_title.get("title"),
                    type="film",
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    size=_format_duration(dict_title.get("duration")),
                    desc=dict_title.get("channel") or dict_title.get("uploader"),
                    year=None,
                )
            )
        except ExtractorError as e:
            console.print(f"[red]Error parsing entry: {e}")

    return len(entries_manager)


# WRAPPING FUNCTIONS
def process_search_result(select_title, selections=None, scrape_serie=None):
    """
    Wrapper for the generalized process_search_result function.
    """
    return base_process_search_result(
        select_title=select_title,
        download_film_func=download_film,
        download_series_func=None,
        media_search_manager=entries_manager,
        table_show_manager=table_show_manager,
        selections=selections,
        scrape_serie=scrape_serie,
    )


def search(
    string_to_search: str | None = None,
    get_onlyDatabase: bool = False,
    direct_item: dict | None = None,
    selections: dict | None = None,
    scrape_serie=None,
):
    """
    Wrapper for the generalized search function.
    """
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
