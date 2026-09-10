from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from urllib.parse import quote

# External library
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


def _slugify(text: str) -> str:
    """Normalize and slugify a text for fuzzy matching."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def _resolve_imdb_id(
    title: str | None, year: int | None, media_type: str
) -> str | None:
    """Resolve an IMDb id from title/year/type via IMDb's public suggestion API."""
    if not title:
        return None

    query = quote(title.strip())
    first = query[0].lower() if query else "x"
    url = f"https://v2.sg.media-imdb.com/suggestion/{first}/{query}.json"

    try:
        response = create_client(headers={"user-agent": get_userAgent()}).get(url)
        response.raise_for_status()
        data = response.json()
    except (HTTPError, ValueError):
        return None

    candidates = (data or {}).get("d") or []
    if not candidates:
        return None

    title_slug = _slugify(title)
    best_match: str | None = None
    best_score = 0.0

    for candidate in candidates:
        candidate_id = candidate.get("id", "")
        if not candidate_id.startswith("tt"):
            continue

        candidate_year = candidate.get("y")
        candidate_title = candidate.get("l") or ""
        ratio = SequenceMatcher(None, title_slug, _slugify(candidate_title)).ratio()

        # Same-media-type detection: series vs movie
        category = str(candidate.get("qid") or candidate.get("q") or "").lower()
        is_series_candidate = any(k in category for k in ("series", "mini", "tv"))
        is_movie_candidate = any(
            k in category for k in ("movie", "feature", "video", "short")
        )
        type_score = 0.0
        if media_type == "tv" and is_series_candidate:
            type_score = 0.4
        elif media_type != "tv" and is_movie_candidate:
            type_score = 0.4

        # Year matching is the strongest signal (Italian titles often differ
        # wildly from the original English ones).
        year_score = 0.0
        if year and candidate_year:
            if candidate_year == year:
                year_score = 1.5
            elif abs(candidate_year - year) == 1:
                year_score = 0.6

        score = year_score + ratio * 0.5 + type_score
        if score > best_score:
            best_match = candidate_id
            best_score = score

    # Require a meaningful match: enough evidence to avoid random hits.
    if best_score < 1.15:
        return None
    return best_match


def title_search(query: str) -> int:
    entries_manager.clear()
    table_show_manager.clear()

    search_url = f"{site_constants.FULL_URL}/api/v1/web/archive"

    try:
        console.print(f"[cyan]Searching: [yellow]{search_url}")
        response = create_client(headers={"user-agent": get_userAgent()}).get(
            search_url, params={"q": query, "limit": 30, "count": 1}
        )
        response.raise_for_status()
        data = response.json()
    except HTTPError as e:
        console.print(
            f"[red]Site: {site_constants.SITE_NAME}, request search error: {e}"
        )
        return 0
    except ValueError as e:
        console.print(
            f"[red]Site: {site_constants.SITE_NAME}, invalid search response: {e}"
        )
        return 0

    if not (data or {}).get("ok"):
        console.print("[yellow]No results found on search page")
        return 0

    items = (data or {}).get("items") or []
    if not items:
        console.print("[yellow]No results found on search page")
        return 0

    with ThreadPoolExecutor(max_workers=10) as executor:
        fut_map = {}
        for item in items:
            try:
                title_id = item.get("id")
                slug = item.get("slug")
                name = item.get("title")
                year = item.get("year")
                media_type = "tv" if item.get("kind") == "series" else "film"

                if title_id is None or slug is None or not name:
                    continue

                title_url = f"{site_constants.FULL_URL}/titles/{title_id}-{slug}"
                fut = executor.submit(_resolve_imdb_id, name, year, media_type)
                fut_map[fut] = (title_id, slug, title_url, name, year, media_type)
            except HTTPError as e:
                console.print(f"[red]Error parsing search entry: {e}")
                continue

        for fut in as_completed(fut_map):
            title_id, slug, title_url, name, year, media_type = fut_map[fut]
            imdb_id = fut.result() or ""

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
