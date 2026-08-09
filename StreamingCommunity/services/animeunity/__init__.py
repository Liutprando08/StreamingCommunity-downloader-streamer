from __future__ import annotations

import urllib.parse

# External library
from httpx import HTTPError
from rich.console import Console
from rich.prompt import Prompt

from StreamingCommunity.services._base import Entries, EntriesManager, site_constants
from StreamingCommunity.services._base.site_search_manager import (
    base_process_search_result,
    base_search,
)
from StreamingCommunity.utils import TVShowManager

# Internal utilities
from StreamingCommunity.utils.http_client import create_client_curl, get_userAgent

# Logic
from .downloader import download_film, download_series

# Variable
indice = 1
_useFor = "Anime"


msg = Prompt()
console = Console()
entries_manager = EntriesManager()
table_show_manager = TVShowManager()


def get_token(user_agent: str) -> dict:
    """
    Retrieve session cookies from the site.
    """
    response = create_client_curl(headers={"user-agent": user_agent}).get(
        site_constants.FULL_URL
    )
    response.raise_for_status()
    all_cookies = {name: value for name, value in response.cookies.items()}

    return {k: urllib.parse.unquote(v) for k, v in all_cookies.items()}


def get_real_title(record: dict) -> str:
    """
    Return the most appropriate title from the record.
    """
    if record.get("title_eng"):
        return record["title_eng"]
    elif record.get("title"):
        return record["title"]
    else:
        return record.get("title_it", "")


def title_search(query: str) -> int:
    """
    Perform anime search on animeunity.so.
    """
    entries_manager.clear()
    table_show_manager.clear()
    seen_titles = set()
    user_agent = get_userAgent()
    data = get_token(user_agent)

    cookies = {
        "XSRF-TOKEN": data.get("XSRF-TOKEN", ""),
        "animeunity_session": data.get("animeunity_session", ""),
    }

    headers = {
        "origin": site_constants.FULL_URL,
        "referer": f"{site_constants.FULL_URL}/",
        "user-agent": user_agent,
        "x-xsrf-token": data.get("XSRF-TOKEN", ""),
    }

    # First call: /livesearch
    try:
        response1 = create_client_curl(headers=headers).post(
            f"{site_constants.FULL_URL}/livesearch",
            cookies=cookies,
            data={"title": query},
        )
        response1.raise_for_status()
        process_results(
            response1.json().get("records", []), seen_titles, entries_manager
        )

    except HTTPError as e:
        console.print(
            f"[red]Site: {site_constants.SITE_NAME}, request search error: {e}"
        )
        return 0

    # Second call: /archivio/get-animes
    try:
        json_data = {
            "title": query,
            "type": False,
            "year": False,
            "order": False,
            "status": False,
            "genres": False,
            "offset": 0,
            "dubbed": False,
            "season": False,
        }
        response2 = create_client_curl(headers=headers).post(
            f"{site_constants.FULL_URL}/archivio/get-animes",
            cookies=cookies,
            json=json_data,
        )
        response2.raise_for_status()
        process_results(
            response2.json().get("records", []), seen_titles, entries_manager
        )

    except HTTPError as e:
        console.print(f"Site: {site_constants.SITE_NAME}, archivio search error: {e}")

    result_count = len(entries_manager)
    return result_count


def process_results(
    records: list, seen_titles: set, entries_manager: EntriesManager
) -> None:
    """
    Add unique results to the media manager.
    """
    for dict_title in records:
        try:
            title_id = dict_title.get("id")
            if title_id in seen_titles:
                continue

            seen_titles.add(title_id)
            dict_title["name"] = get_real_title(dict_title)

            entry = Entries.__new__(Entries)
            entry.id = title_id
            entry.name = dict_title.get("name", "")
            entry.type = dict_title.get("type", "")
            entry.url = dict_title.get("url", "")
            entry.size = dict_title.get("size", "")
            entry.score = dict_title.get("score", "")
            entry.desc = dict_title.get("desc", "")
            entry.slug = dict_title.get("slug", "")
            entry.year = str(dict_title.get("year", ""))
            entry.provider_language = dict_title.get("provider_language", "")
            entry.tmdb_id = dict_title.get("tmdb_id", "")

            entries_manager.add(entry)

        except HTTPError as e:
            print(f"Error parsing a title entry: {e}")


# WRAPPING FUNCTIONS
def process_search_result(select_title, selections=None, scrape_serie=None):
    """
    Wrapper for the generalized process_search_result function.
    """
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

