"""Serialisable models mirroring ``internal/zlib/model.go``.

Each model keeps the Go JSON field names and ``omitempty`` behaviour so a
Python caller can emit the same payloads as ``zlib --json``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .constants import Extension, Language, OrderOption


def _omit_none(value: Any) -> bool:
    return value is None or value == "" or value == []


@dataclass
class Book:
    id: str = ""
    hash: str = ""
    isbn: str = ""
    isbn10: str = ""
    isbn13: str = ""
    url: str = ""
    cover: str = ""
    name: str = ""
    authors: list[str] = field(default_factory=list)
    publisher: str = ""
    year: str = ""
    language: str = ""
    extension: str = ""
    size: str = ""
    rating: str = ""
    quality: str = ""
    description: str = ""
    categories: str = ""
    edition: str = ""
    pages: str = ""
    download_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "hash": self.hash or None,
            "isbn": self.isbn or None,
            "isbn_10": self.isbn10 or None,
            "isbn_13": self.isbn13 or None,
            "url": self.url,
            "cover": self.cover or None,
            "name": self.name,
            "authors": self.authors or None,
            "publisher": self.publisher or None,
            "year": self.year or None,
            "language": self.language or None,
            "extension": self.extension or None,
            "size": self.size or None,
            "rating": self.rating or None,
            "quality": self.quality or None,
            "description": self.description or None,
            "categories": self.categories or None,
            "edition": self.edition or None,
            "pages": self.pages or None,
            "download_url": self.download_url or None,
        }

    def json_dict(self) -> dict[str, Any]:
        """Return the dictionary with empty optional fields removed."""
        return {key: value for key, value in self.to_dict().items() if not _omit_none(value)}


@dataclass
class SearchResult:
    books: list[Book] = field(default_factory=list)
    page: int = 0
    total_pages: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "books": [book.json_dict() for book in self.books],
            "page": self.page,
            "total_pages": self.total_pages,
        }


@dataclass
class DownloadLimit:
    daily_amount: int = 0
    daily_allowed: int = 0
    daily_remaining: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "daily_amount": self.daily_amount,
            "daily_allowed": self.daily_allowed,
            "daily_remaining": self.daily_remaining,
        }


@dataclass
class UserProfile:
    download_limit: DownloadLimit = field(default_factory=DownloadLimit)
    id: str = ""
    name: str = ""
    email: str = ""
    kindle_email: str = ""
    premium: bool | None = None
    confirmed: bool | None = None
    donations_active: bool | None = None
    donations_expire: str = ""
    personal_domains: list[str] = field(default_factory=list)
    quota_known: bool = False

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            **self.download_limit.to_dict(),
            "id": self.id or None,
            "name": self.name or None,
            "email": self.email or None,
            "kindle_email": self.kindle_email or None,
            "premium": self.premium,
            "confirmed": self.confirmed,
            "donations_active": self.donations_active,
            "donations_expire": self.donations_expire or None,
            "personal_domains": self.personal_domains or None,
            "quota_known": self.quota_known,
        }
        return data

    def json_dict(self) -> dict[str, Any]:
        return {key: value for key, value in self.to_dict().items() if value is not None}


@dataclass
class DownloadHistoryItem:
    id: str = ""
    hash: str = ""
    name: str = ""
    authors: list[str] = field(default_factory=list)
    url: str = ""
    download_url: str = ""
    extension: str = ""
    size: str = ""
    date: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id or None,
            "hash": self.hash or None,
            "name": self.name,
            "authors": self.authors or None,
            "url": self.url,
            "download_url": self.download_url or None,
            "extension": self.extension or None,
            "size": self.size or None,
            "date": self.date,
        }

    def json_dict(self) -> dict[str, Any]:
        return {key: value for key, value in self.to_dict().items() if value is not None}


@dataclass
class DownloadHistoryResult:
    items: list[DownloadHistoryItem] = field(default_factory=list)
    page: int = 0
    total_pages: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [item.json_dict() for item in self.items],
            "page": self.page,
            "total_pages": self.total_pages,
        }


@dataclass
class Booklist:
    name: str = ""
    url: str = ""
    description: str = ""
    author: str = ""
    count: str = ""
    views: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "description": self.description or None,
            "author": self.author or None,
            "count": self.count or None,
            "views": self.views or None,
        }

    def json_dict(self) -> dict[str, Any]:
        return {key: value for key, value in self.to_dict().items() if value is not None}


@dataclass
class BooklistResult:
    lists: list[Booklist] = field(default_factory=list)
    page: int = 0
    total_pages: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "lists": [item.json_dict() for item in self.lists],
            "page": self.page,
            "total_pages": self.total_pages,
        }


@dataclass
class SearchOptions:
    exact: bool = False
    from_year: int = 0
    to_year: int = 0
    languages: list[Language | str] = field(default_factory=list)
    extensions: list[Extension | str] = field(default_factory=list)
    order: OrderOption | str | None = None


@dataclass
class FullTextSearchOptions(SearchOptions):
    phrase: bool = False


@dataclass
class DownloadResult:
    file_path: str = ""
    size: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"file_path": self.file_path, "size": self.size}


@dataclass
class BookReference:
    """A parsed ``id:hash`` book reference."""

    id: str
    hash: str

    def __str__(self) -> str:
        return f"{self.id}:{self.hash}"
