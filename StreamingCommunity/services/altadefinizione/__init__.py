from __future__ import annotations

import html as html_module
import json
import re

# External library
from bs4 import BeautifulSoup
from httpx2 import HTTPError
from rich.prompt import Prompt

from StreamingCommunity.services._base import Entries, EntriesManager, site_constants
from StreamingCommunity.services._base.site_search_manager import (
    base_process_search_result,
    base_search,
)

# Internal utilities
from StreamingCommunity.utils import TVShowManager
from StreamingCommunity.utils.console.shared import console
from StreamingCommunity.utils.domain_check import check_streamingcommunity_domain
from StreamingCommunity.utils.http_client import create_client, get_userAgent

# Variable
indice = 24
_useFor = "Film_Serie"
IMDB_RE = re.compile(r"tt(\d+)")

msg = Prompt()
entries_manager = EntriesManager()
table_show_manager = TVShowManager()
_domain_checked = False


def _search_archive(query: str) -> int | None:
    """Primary search through the Next.js JSON API.

    Returns the number of results, or None when the API is unavailable so the
    caller can fall back to the legacy HTML scraper.
    """
    search_url = f"{site_constants.FULL_URL}/api/v1/web/archive"
    params = {"q": query, "limit": 30, "count": 1}

    try:
        console.print(f"[cyan]Searching: [yellow]{search_url}")
        response = create_client().get(search_url, params=params)
        response.raise_for_status()
        data = response.json()
    except (HTTPError, ValueError) as e:
        console.print(
            f"[red]Site: {site_constants.SITE_NAME}, archive search error: {e}"
        )
        return None

    items = data.get("items") if isinstance(data, dict) else []
    if items is None:
        # Degraded API response: fall back to the legacy HTML scraper instead
        # of raising (the caller only falls back on a ``None`` return).
        console.print(
            "[yellow]Archive API returned no items, falling back to HTML search"
        )
        return None
    for item in items:
        entry = _build_entry(item)
        if entry:
            entries_manager.add(entry)

    return len(entries_manager)


def _build_entry(item: dict) -> Entries | None:
    """Build an Entries row from a `/api/v1/web/archive` API item."""
    title_id = item.get("id") or item.get("legacyId")
    slug = item.get("slug")
    if not title_id or not slug:
        return None

    kind = item.get("kind") or ""
    media_type = "tv" if kind == "series" else "film"

    entry = Entries(
        id=int(title_id),
        name=item.get("title") or slug.replace("-", " ").title(),
        type=media_type,
        url=f"{site_constants.FULL_URL}/titles/{title_id}-{slug}-streaming",
        slug=slug,
        year=str(item.get("year") or ""),
        imdb_id=item.get("imdbId") or "",
    )
    entry.size = ""
    entry.score = str(item.get("rating") or "")
    entry.desc = item.get("plot") or ""
    entry.provider_language = ""
    return entry


def title_search(query: str) -> int:
    entries_manager.clear()
    table_show_manager.clear()

    count = _search_archive(query)
    if count is not None:
        return count
    return 404


def process_search_result(select_title, selections=None, scrape_serie=None):
    import os

    streaming_mode = os.environ.get("STREAMING_MODE") == "1"

    return base_process_search_result(
        select_title=select_title,
        download_film_func=stream_film if streaming_mode else download_film,
        download_series_func=stream_series if streaming_mode else download_series,
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
