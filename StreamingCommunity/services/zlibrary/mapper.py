# 19.11.26 - Map engine ``Book`` objects onto the shared ``Entries`` shape.
#
# The TUI and the CLI both consume ``Entries``, so everything a screen may
# render has to live on it as a plain attribute. Only two extras are added
# (``authors`` and ``extension``): the downloader rebuilds the EAPI URL from
# ``id`` ("<book id>:<hash>"), so no internal URLs leak into the UI.

from __future__ import annotations

import logging

# Engine
from StreamingCommunity.zlib_engine import Book

# Internal utilities
from StreamingCommunity.services._base import Entries

logger = logging.getLogger(__name__)


def book_key(book: Book) -> str:
    """Return the stable ``<id>:<hash>`` handle stored in ``entry.id``."""
    return f"{book.id}:{book.hash}"


def split_book_key(value: object) -> tuple[str, str]:
    """Split ``<id>:<hash>`` back into its parts."""
    book_id, _, book_hash = str(value or "").partition(":")
    return book_id.strip(), book_hash.strip()


def _author_line(book: Book) -> str:
    return ", ".join(name for name in book.authors if name)


def book_to_entry(book: Book) -> Entries | None:
    """Convert one search hit, or return ``None`` when it cannot be fetched."""
    if not (book.id and book.hash):
        logger.debug("zlibrary: skipping book without id/hash: %r", book.name)
        return None

    return Entries(
        id=book_key(book),
        name=book.name or "Sconosciuto",
        type="book",
        url=book.url,
        size=book.size,
        desc=book.description,
        year=book.year,
        provider_language=book.language,
        authors=_author_line(book),
        extension=book.extension,
    )


def books_to_entries(books: list[Book]) -> list[Entries]:
    entries: list[Entries] = []
    for book in books:
        entry = book_to_entry(book)
        if entry is not None:
            entries.append(entry)
    return entries


__all__ = ["book_key", "split_book_key", "book_to_entry", "books_to_entries"]
