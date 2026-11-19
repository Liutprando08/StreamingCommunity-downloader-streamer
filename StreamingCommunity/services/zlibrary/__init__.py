# 19.11.26 - Z-Library: book catalog backed by the vendored zlib engine.
#
# Search and downloads require a Z-Library account (see Conf/login.json →
# "zlibrary"). Results are plain ``Entries`` with ``type="book"`` so the CLI
# picker and the TUI both render them without special cases; the downloader
# resolves the EAPI file endpoint from ``entry.id`` ("<id>:<hash>").

from __future__ import annotations

# Engine
from StreamingCommunity.zlib_engine import NotLoggedIn, SessionExpired, ZlibError

# Internal utilities
from StreamingCommunity.services._base import EntriesManager
from StreamingCommunity.services._base.site_search_manager import get_select_title
from StreamingCommunity.utils import TVShowManager
from StreamingCommunity.utils.console.shared import console

# Logic
from . import client as zclient
from .downloader import download_book
from .mapper import book_to_entry

# Variable
indice = 26
_useFor = "Books"

msg = None  # set lazily; only the interactive path needs it

entries_manager = EntriesManager()
table_show_manager = TVShowManager()


def _not_logged_in_hint() -> None:
    console.print(f"\n[red]{zclient.missing_credentials_message()}")


def title_search(query: str) -> int:
    """Search Z-Library and load the hits into ``entries_manager``."""
    entries_manager.clear()
    table_show_manager.clear()

    query = (query or "").strip()
    if not query:
        return 0

    try:
        client = zclient.get_client()
        result = client.search(
            query,
            page=1,
            count=zclient.configured_search_count(),
            options=zclient.search_options(),
        )
    except NotLoggedIn:
        _not_logged_in_hint()
        return 0
    except ZlibError as error:
        console.print(f"\n[red]Z-Library: {error}")
        return 0

    for book in result.books:
        entry = book_to_entry(book)
        if entry is not None:
            entries_manager.add(entry)

    return len(entries_manager)


def get_full_description(entry) -> str | None:
    """Return the synopsis, fetching it when the search payload omitted it."""
    description = str(getattr(entry, "desc", "") or "").strip()
    if description:
        return description

    try:
        client = zclient.get_client()
        book = client.fetch_book(str(getattr(entry, "id", "") or ""))
    except (ZlibError, ValueError):
        return None

    if book.description:
        entry.desc = book.description
    return book.description or None


def process_search_result(
    select_title, selections=None, scrape_serie=None
) -> bool:
    """Download the selected book (the CLI picker calls this)."""
    if not select_title:
        console.print("[yellow]Nessun libro selezionato.")
        return False

    result = download_book(select_title)
    entries_manager.clear()
    table_show_manager.clear()
    return result is not None


def search(
    string_to_search: str | None = None,
    get_onlyDatabase: bool = False,
    direct_item: dict | None = None,
    selections: dict | None = None,
    scrape_serie=None,
):
    """CLI entry point, mirroring ``base_search`` for the ``book`` type."""
    if direct_item:
        from StreamingCommunity.services._base import Entries

        return process_search_result(Entries(**direct_item), selections, scrape_serie)

    global msg
    if string_to_search is not None:
        query = string_to_search.strip()
    else:
        if msg is None:
            from rich.prompt import Prompt

            msg = Prompt()
        query = msg.ask("\n[purple]Insert a word to search in [green]Z-Library").strip()

    if not query:
        return False

    total = title_search(query)
    entries_manager.sort_by_fuzzy_score(query)

    if get_onlyDatabase:
        return entries_manager

    if total <= 0:
        console.print(f"\n[red]Nothing matching was found for[white]: [purple]{query}")
        return False

    select_title = get_select_title(table_show_manager, entries_manager)
    return process_search_result(select_title, selections, scrape_serie)


__all__ = [
    "indice",
    "_useFor",
    "entries_manager",
    "table_show_manager",
    "title_search",
    "get_full_description",
    "process_search_result",
    "search",
    "SessionExpired",
]
