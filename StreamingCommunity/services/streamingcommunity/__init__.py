from __future__ import annotations

import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

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
from StreamingCommunity.utils.http_client import create_client, get_userAgent
from StreamingCommunity.utils.console.shared import console

# Logic
from .downloader import download_film, download_series, stream_film, stream_series

# Variable
indice = 0
_useFor = "Film_Serie"


msg = Prompt()
entries_manager = EntriesManager()
table_show_manager = TVShowManager()


def _extract_imdb_id(soup):
    ids = []
    for sel, attr, pattern in [
        (
            '[style*="/uploads/backdrops/"]',
            "style",
            r"/uploads/backdrops/(tt\d+)\.webp",
        ),
        ('[src*="/uploads/logos/"]', "src", r"/uploads/logos/(tt\d+)\.webp"),
        ('img[src*="/uploads/posters/"]', "src", r"/uploads/posters/(tt\d+)\.webp"),
    ]:
        el = soup.select_one(sel)
        if el:
            match = re.search(pattern, el.get(attr, ""))
            if match:
                ids.append(match.group(1))
    if not ids:
        return None
    return Counter(ids).most_common(1)[0][0]


def _is_series(soup):
    if 'data-category="Serie TV"' in str(soup):
        return True
    return bool(soup.select_one("#episodi"))


def _fetch_title_details(title_url, name):
    try:
        client = create_client(headers={"user-agent": get_userAgent()})
        response = client.get(title_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        h1 = soup.select_one("h1")
        clean_name = h1.text.strip() if h1 else name

        imdb_id = _extract_imdb_id(soup)
        is_series = _is_series(soup)
        return clean_name, imdb_id, is_series
    except HTTPError:
        return None, None, None


def title_search(query: str) -> int:
    entries_manager.clear()
    table_show_manager.clear()

    search_url = f"{site_constants.FULL_URL}/index.php?do=search"
    headers = {
        "user-agent": get_userAgent(),
        "content-type": "application/x-www-form-urlencoded",
    }
    data = {"do": "search", "subaction": "search", "story": query}

    try:
        console.print(f"[cyan]Searching: [yellow]{search_url}")
        response = create_client(headers=headers).get(search_url, params=data)
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

    tile_info = []
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
                href if href.startswith("http") else f"{site_constants.FULL_URL}{href}"
            )

            img = tile.select_one("img")
            if img and img.get("alt"):
                name = img.get("alt")
            elif img and img.get("title"):
                name = img.get("title")
            else:
                name = slug.replace("-", " ").title()

            tile_info.append((title_id, slug, title_url, name))
        except HTTPError as e:
            console.print(f"[red]Error parsing search entry: {e}")
            continue

    with ThreadPoolExecutor(max_workers=10) as executor:
        fut_map = {
            executor.submit(_fetch_title_details, url, name): (tid, slug, url, name)
            for tid, slug, url, name in tile_info
        }
        for fut in as_completed(fut_map):
            tid, slug, url, name = fut_map[fut]
            clean_name, imdb_id, is_series = fut.result()
            if imdb_id is None:
                imdb_id = ""

            media_type = "tv" if is_series else "film"

            entry = Entries.__new__(Entries)
            entry.id = int(tid)
            entry.name = clean_name or name
            entry.type = media_type
            entry.url = url
            entry.size = ""
            entry.score = ""
            entry.desc = ""
            entry.slug = slug
            entry.year = ""
            entry.provider_language = ""
            entry.imdb_id = imdb_id or ""

            entries_manager.add(entry)

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
