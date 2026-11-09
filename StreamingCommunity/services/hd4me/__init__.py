# 09.11.26 - HD4ME: download-only catalog backed by the site's cached JSON index.

from __future__ import annotations

from StreamingCommunity.services._base import EntriesManager, site_constants
from StreamingCommunity.services._base.site_search_manager import (
    base_process_search_result,
    base_search,
)

# Internal utilities
from StreamingCommunity.utils import TVShowManager
from StreamingCommunity.utils.console.shared import console

# Logic
from .downloader import download_film
from .scrapper import get_full_description, get_index, search_index

# Variable
indice = 25
_useFor = "Film_Serie"

entries_manager = EntriesManager()
table_show_manager = TVShowManager()


def title_search(query: str) -> int:
    """Search the current HD4ME index.

    The index is downloaded on every search so new releases are visible without
    restarting the app; the bundled ``hd4me.json`` is only an offline fallback.
    """
    entries_manager.clear()
    table_show_manager.clear()

    index = get_index()
    if not index:
        console.print("[red]HD4ME: no index available")
        return 0

    for entry in search_index(query, index):
        entries_manager.add(entry)

    console.print(f"[green]HD4ME: {len(entries_manager)} result(s) found")
    return len(entries_manager)


def process_search_result(select_title, selections=None, scrape_serie=None):
    """Wrapper for the generalized process_search_result function."""
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
    """Wrapper for the generalized search function."""
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
