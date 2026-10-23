# 21.03.25 - AnimeWorld service

from __future__ import annotations

import os
from urllib.parse import urljoin

# External library
from bs4 import BeautifulSoup
from httpx2 import HTTPError
from rich.prompt import Prompt

# Internal utilities
from StreamingCommunity.services._base import Entries, EntriesManager, site_constants
from StreamingCommunity.services._base.site_search_manager import (
    base_process_search_result,
    base_search,
)
from StreamingCommunity.utils import TVShowManager
from StreamingCommunity.utils.console.shared import console
from StreamingCommunity.utils.domain_check import check_animeworld_domain
from StreamingCommunity.utils.http_client import create_client, get_headers

# Logic
from .downloader import (
    download_film,
    download_series,
    stream_film,
    stream_series,
)

# Variable
indice = 6
_useFor = "Anime"

msg = Prompt()
entries_manager = EntriesManager()
table_show_manager = TVShowManager()
_domain_checked = False


def _ensure_domain() -> None:
    """Refresh the AnimeWorld domain once per process, before the first search."""
    global _domain_checked
    if _domain_checked:
        return
    _domain_checked = True
    try:
        check_animeworld_domain()
    except HTTPError as exc:  # a failed check must not block the search
        console.print(f"[yellow]Domain check skipped: {exc}")


def _status_type(status_div) -> tuple[str, bool, bool]:
    """Map the card status classes to a generic type, DUB and special flags."""
    if status_div is None:
        return "TV", False, False

    is_dubbed = status_div.find("div", class_="dub") is not None
    is_special = status_div.find("div", class_="special") is not None

    if status_div.find("div", class_="movie") is not None:
        return "Movie", is_dubbed, is_special
    if status_div.find("div", class_="ova") is not None:
        return "OVA", is_dubbed, is_special
    if status_div.find("div", class_="ona") is not None:
        return "ONA", is_dubbed, is_special
    if is_special:
        # The shared CLI only knows TV/Serie/OVA/ONA/Show as series types.
        # Specials are single-episode series, so expose them through ONA.
        return "ONA", is_dubbed, True
    return "TV", is_dubbed, False


def _build_entry(element) -> Entries | None:
    img = element.find("img")
    href = element.get("href")
    if img is None or not href:
        return None

    name = str(img.get("alt") or "").strip()
    if not name:
        return None

    base_url = site_constants.FULL_URL.rstrip("/")
    url = urljoin(f"{base_url}/", str(href))
    status_div = element.find("div", class_="status")
    anime_type, is_dubbed, is_special = _status_type(status_div)

    tip = element.get("data-tip")
    tip_url = urljoin(f"{base_url}/", str(tip)) if tip else None
    anime_id = None
    if tip:
        anime_id = str(tip).rstrip("/").rsplit("/", 1)[-1]

    return Entries(
        id=anime_id,
        name=name,
        type=anime_type,
        url=url,
        slug=str(href),
        year="",
        provider_language="ITA" if is_dubbed else "Sub ITA",
        image=urljoin(f"{base_url}/", str(img.get("src") or "")),
        dub=is_dubbed,
        is_special=is_special,
        _tip_url=tip_url,
    )


def get_full_description(entry) -> str | None:
    """Read the tooltip synopsis for a search entry, on demand."""
    tip_url = getattr(entry, "_tip_url", None)
    if not tip_url:
        return None

    try:
        with create_client(headers=get_headers()) as client:
            response = client.get(str(tip_url))
            response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        desc = soup.find("p", class_="desc")
        if desc is not None:
            text = " ".join(desc.get_text(" ", strip=True).split())
            if text:
                return text
    except Exception:
        return None
    return None


def title_search(query: str) -> int:
    """Search AnimeWorld and fill ``entries_manager``."""
    _ensure_domain()
    entries_manager.clear()
    table_show_manager.clear()

    base_url = site_constants.FULL_URL.rstrip("/")
    search_url = f"{base_url}/search"
    console.print(f"[cyan]Search url: [yellow]{search_url}?keyword={query}")

    try:
        with create_client(headers=get_headers()) as client:
            response = client.get(search_url, params={"keyword": query})
            response.raise_for_status()
    except Exception as exc:
        console.print(
            f"[red]Site: {site_constants.SITE_NAME}, request search error: {exc}"
        )
        return 0

    soup = BeautifulSoup(response.text, "html.parser")
    seen: set[str] = set()

    for element in soup.select("a.poster"):
        try:
            entry = _build_entry(element)
            if entry is None or entry.url in seen:
                continue
            if entry.url is not None:
                seen.add(entry.url)
            entries_manager.add(entry)
        except HTTPError as exc:
            console.print(f"[yellow]Error parsing an AnimeWorld entry: {exc}")

    return len(entries_manager)


# WRAPPING FUNCTIONS
def process_search_result(select_title, selections=None, scrape_serie=None):
    """Wrapper for the generalized process_search_result function."""
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
