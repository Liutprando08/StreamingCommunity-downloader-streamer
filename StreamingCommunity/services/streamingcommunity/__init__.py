from __future__ import annotations

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
from StreamingCommunity.utils.http_client import create_client, get_userAgent

# Logic
from .downloader import download_film, download_series, stream_film, stream_series

# Variable
indice = 0
_useFor = "Film_Serie"


msg = Prompt()
entries_manager = EntriesManager()
table_show_manager = TVShowManager()


def title_search(query: str) -> int:
    entries_manager.clear()
    table_show_manager.clear()

    search_url = f"{site_constants.FULL_URL}/index.php?do=search"
    headers = {
        "user-agent": get_userAgent(),
        "content-type": "application/x-www-form-urlencoded",
    }
    params = {"do": "search", "subaction": "search", "story": query}

    try:
        console.print(f"[cyan]Searching: [yellow]{search_url}")
        response = create_client(headers=headers).get(search_url, params=params)
        response.raise_for_status()
    except HTTPError as e:
        console.print(
            f"[red]Site: {site_constants.SITE_NAME}, request search error: {e}"
        )
        return 0

    soup = BeautifulSoup(response.text, "html.parser")
    tiles = soup.select(".slider-tile")

    if not tiles:
        console.print("[yellow]No results found on search page")
        return 0

    for tile in tiles:
        try:
            link = tile.select_one('a[href*="/titles/"]')
            if not link:
                continue

            href = link.get("href", "")
            if not isinstance(href, str):
                continue
            match = re.search(r"/titles/(\d+)-(.*?)\.html", href)
            if not match:
                continue

            title_id = match.group(1)
            slug = match.group(2)
            title_url = (
                href
                if href.startswith("http")
                else f"{site_constants.FULL_URL}{href}"
            )

            name = link.get("data-title") or slug.replace("-", " ").title()
            year = link.get("data-year") or ""
            category = link.get("data-category") or ""
            media_type = "tv" if "Serie TV" in category else "film"

            imdb_id = ""
            img = tile.select_one("img[src*='/uploads/posters/']")
            if img:
                poster_match = re.search(r"/(tt\d+)\.webp", img.get("src", ""))
                if poster_match:
                    imdb_id = poster_match.group(1)

            entry = Entries.__new__(Entries)
            entry.id = int(title_id)
            entry.name = name
            entry.type = media_type
            entry.url = title_url
            entry.size = ""
            entry.score = ""
            entry.desc = ""
            entry.slug = slug
            entry.year = str(year) if year else ""
            entry.provider_language = ""
            entry.imdb_id = imdb_id

            entries_manager.add(entry)
        except HTTPError as e:
            console.print(f"[red]Error parsing search entry: {e}")
            continue

    return len(entries_manager)


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
