# Book providers for the TUI (zlibrary).
#
# A book is one downloadable file, so books use the atomic flow: search ->
# detail -> queue. Unlike the other atomic providers, the queue kind is
# "book" so the activity screen reports "Book" instead of "Film".
#
# There is only one book service today. It still gets its own provider kind
# (``BookProvider``) because book metadata (authors, language, format) and the
# "Libri" sector are genuinely different from video results, and a new book
# service would only add a spec row.

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from .base import service_search_lock

DEFAULT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("Titolo", "name"),
    ("Autore", "authors"),
    ("Anno", "year"),
    ("Lingua", "provider_language"),
    ("Formato", "extension"),
)


@dataclass(frozen=True)
class BookSpec:
    """Everything that varies between two book services."""

    name: str
    alias: str
    module: str
    columns: tuple[tuple[str, str], ...] = DEFAULT_COLUMNS


class BookProvider:
    """One book service, configured by its :class:`BookSpec`."""

    flow = "atomic"
    supports_streaming = False
    supports_seasons = False
    category = "Books"
    sector = "books"
    queue_kind = "book"
    film_icon = "📖"
    film_label = "Libro"

    def __init__(self, spec: BookSpec) -> None:
        self._spec = spec
        self._service: Any = None

        self.name = spec.name
        self.alias = spec.alias

    # ── lazy service access ───────────────────────────────────────────────
    def _module(self):
        """Lazy import so TUI startup stays light and CLI stays untouched."""
        if self._service is None:
            self._service = importlib.import_module(
                f"StreamingCommunity.services.{self._spec.module}"
            )
        return self._service

    def _downloader(self):
        return importlib.import_module(
            f"StreamingCommunity.services.{self._spec.module}.downloader"
        )

    # ── protocol ──────────────────────────────────────────────────────────
    def search(self, query: str) -> list[Any]:
        service = self._module()
        with service_search_lock(self._spec.module):
            service.entries_manager.clear()
            service.title_search(query)
            # The service swallows engine errors so the CLI can print them and
            # keep running; the TUI has a status line, so surface the reason
            # instead of showing a silent empty table.
            error = getattr(service, "last_error", None)
            if error and not service.entries_manager.media_list:
                raise RuntimeError(error)
            service.entries_manager.sort_by_fuzzy_score(query)
            return list(service.entries_manager.media_list)

    def result_columns(self) -> tuple[tuple[str, str], ...]:
        return self._spec.columns

    def is_series(self, entry: Any) -> bool:
        # A book is always a single, indivisible download.
        return False

    def entry_description(self, entry: Any) -> str | None:
        try:
            return self._module().get_full_description(entry)
        except Exception:
            return None

    def download_book(self, entry: Any) -> Any:
        return self._downloader().download_book(entry)

    def download_film(self, entry: Any) -> Any:
        # The atomic queue path calls ``download_film``; route it to the book
        # downloader so both entry points behave identically.
        return self.download_book(entry)

    def stream_film(self, entry: Any) -> None:
        # Never offered: books have no stream path.
        return None

    def download_episode(self, *args: Any) -> None:
        return None

    def stream_episode(self, *args: Any) -> None:
        return None


# ── the book services ──────────────────────────────────────────────────────
BOOK_SPECS: dict[str, BookSpec] = {
    spec.alias: spec
    for spec in (
        BookSpec(
            name="Z-Library",
            alias="zlibrary",
            module="zlibrary",
        ),
    )
}


__all__ = ["BOOK_SPECS", "BookSpec", "BookProvider", "DEFAULT_COLUMNS"]
