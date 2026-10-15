# 16.10.25 - MangaWorld service

from __future__ import annotations

import json
import re

# External library
from bs4 import BeautifulSoup
from httpx2 import HTTPError
from rich.prompt import Prompt

from StreamingCommunity.services._base import Entries, EntriesManager, site_constants
from StreamingCommunity.services._base.site_search_manager import base_search

# Internal utilities
from StreamingCommunity.utils import TVShowManager
from StreamingCommunity.utils.console.shared import console
from StreamingCommunity.utils.http_client import create_client

# Logic
from .downloader import download_manga, stream_chapter

# Variable
indice = 23
_useFor = "Manga"

msg = Prompt()
entries_manager = EntriesManager()
table_show_manager = TVShowManager()

_description_cache: dict[str, str] = {}


def _search_html(query: str) -> int:
    """Search MangaWorld's archive page and parse the resulting cards."""
    search_url = f"{site_constants.FULL_URL}/archive"
    params = {"keyword": query}

    try:
        console.print(f"[cyan]Searching: [yellow]{search_url}")
        response = create_client().get(search_url, params=params)
        response.raise_for_status()
    except HTTPError as e:
        console.print(
            f"[red]Site: {site_constants.SITE_NAME}, request search error: {e}"
        )
        return 0

    soup = BeautifulSoup(response.text, "html.parser")
    tiles = soup.select(".entry, .manga-card, .comic, .book, .slider-tile")

    if not tiles:
        console.print("[yellow]No results found on search page")
        return 0

    seen_ids: set[str] = set()
    for tile in tiles:
        try:
            link = tile.select_one('a[href*="/manga/"]')
            if not link:
                continue

            href = link.get("href", "")
            if not isinstance(href, str):
                continue
            match = re.search(r"/manga/(\d+)[-/]([^/?#]+)", href)
            if not match:
                continue

            title_id = match.group(1)
            if title_id in seen_ids:
                continue
            seen_ids.add(title_id)
            slug = match.group(2).rstrip("/")
            title_url = (
                href if href.startswith("http") else f"{site_constants.FULL_URL}{href}"
            )

            name = (
                link.get("title")
                or (tile.select_one("img") and tile.select_one("img").get("alt"))
                or slug.replace("-", " ").title()
            )
            year = link.get("data-year") or ""
            img = tile.select_one("img")
            poster = img.get("src", "") if img else ""

            entry = Entries(
                id=int(title_id),
                name=str(name),
                type="manga",
                url=title_url,
            )
            entry.size = ""
            entry.score = ""
            entry.desc = ""
            entry.slug = slug
            entry.year = str(year) if year else ""
            entry.provider_language = ""
            entry.imdb_id = ""
            entry.image = poster

            entries_manager.add(entry)
        except (HTTPError, ValueError) as e:
            console.print(f"[red]Error parsing search entry: {e}")
            continue

    return len(entries_manager)


def title_search(query: str) -> int:
    entries_manager.clear()
    table_show_manager.clear()

    return _search_html(query)


def process_search_result(select_title, selections=None, scrape_serie=None):
    import os

    if not select_title:
        console.print("[yellow]No title selected or selection cancelled.")
        return False

    season_selection = None
    episode_selection = None
    if selections:
        season_selection = selections.get("season") or selections.get("volume")
        episode_selection = selections.get("episode") or selections.get("chapter")
        if not scrape_serie:
            scrape_serie = selections.get("scrape_serie")

    streaming_mode = os.environ.get("STREAMING_MODE") == "1"

    if streaming_mode:
        result = stream_chapter(select_title, season_selection, episode_selection, scrape_serie)
    else:
        result = download_manga(select_title, season_selection, episode_selection, scrape_serie)

    if table_show_manager:
        table_show_manager.clear()

    if result is None or result is False:
        console.print("[red]Manga download failed.")
        return False
    return True


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


def _extract_plot(page: str) -> str | None:
    """Extract the full synopsis from the `"trama"` field of the page payload."""
    marker = '"trama":'
    index = page.find(marker)
    while index != -1:
        try:
            value, _ = json.JSONDecoder().raw_decode(page[index + len(marker) :])
        except ValueError:
            value = None
        if isinstance(value, str) and value.strip():
            return value.strip()
        index = page.find(marker, index + len(marker))
    return None


def get_full_description(entry: Entries) -> str | None:
    url = getattr(entry, "url", None)
    if not url:
        return None
    if url in _description_cache:
        return _description_cache[url]
    try:
        response = create_client().get(url)
        response.raise_for_status()
    except HTTPError:
        return None
    except Exception:
        return None
    description = _extract_plot(response.text or "")
    if description:
        _description_cache[url] = description
    return description
