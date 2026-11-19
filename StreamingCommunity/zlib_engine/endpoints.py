"""EAPI feeds, saved books, profile and download history.

Mirrors ``internal/zlib/eapi_feed.go``, ``eapi_saved.go``, ``eapi_profile.go``
and ``eapi_history_delete.go``.
"""

from __future__ import annotations

from typing import Any

from .client import Client
from .eapi import (
    decode_json,
    eapi_flag,
    eapi_int,
    eapi_request,
    eapi_string,
    map_eapi_book,
)
from .errors import ZlibError
from .model import (
    Book,
    DownloadHistoryItem,
    DownloadHistoryResult,
    DownloadLimit,
    SearchResult,
    UserProfile,
)

RECOMMENDED_BOOKS_PATH = "/eapi/user/book/recommended"
MOST_POPULAR_BOOKS_PATH = "/eapi/book/most-popular"


def _books_field(result: dict[str, Any], fallback: str) -> list[dict[str, Any]]:
    books = result.get("books")
    return [item for item in books if isinstance(item, dict)] if isinstance(books, list) else []


def _rejection(result: dict[str, Any], fallback: str) -> str:
    error = result.get("error")
    return error if isinstance(error, str) and error else fallback


def _pagination(result: dict[str, Any], page: int) -> tuple[int, int]:
    pagination = result.get("pagination")
    if not isinstance(pagination, dict):
        pagination = {}
    current = eapi_int(pagination.get("current")) or page
    return current, eapi_int(pagination.get("total_pages"))


def _book_feed(client: Client, path: str) -> list[Book]:
    body = eapi_request(client, "GET", path, None)
    result = decode_json(body, "EAPI book list")
    if not isinstance(result, dict):
        raise ZlibError("zlibrary: invalid EAPI book list response: expected an object")
    if result.get("success") != 1:
        raise ZlibError(f"zlibrary: EAPI book list failed: {_rejection(result, 'book list request was rejected')}")
    books: list[Book] = []
    for item in _books_field(result, "book list"):
        book = map_eapi_book(client, item)
        if not book.id or not book.hash:
            raise ZlibError("zlibrary: EAPI book list entry is missing id or hash")
        books.append(book)
    return books


def recommended_books(client: Client) -> list[Book]:
    return _book_feed(client, RECOMMENDED_BOOKS_PATH)


def most_popular_books(client: Client) -> list[Book]:
    return _book_feed(client, MOST_POPULAR_BOOKS_PATH)


def saved_books(client: Client, page: int = 1) -> SearchResult:
    page = max(page, 1)
    body = eapi_request(
        client, "GET", "/eapi/user/book/saved", [("page", page), ("limit", 50)]
    )
    result = decode_json(body, "EAPI saved books")
    if not isinstance(result, dict):
        raise ZlibError("zlibrary: invalid EAPI saved books response: expected an object")
    if result.get("success") != 1:
        raise ZlibError(
            f"zlibrary: EAPI saved books failed: {_rejection(result, 'saved books request was rejected')}"
        )
    books = [map_eapi_book(client, item) for item in _books_field(result, "saved books")]
    current, total = _pagination(result, page)
    return SearchResult(books=books, page=current, total_pages=total)


def get_profile(client: Client) -> UserProfile:
    body = eapi_request(client, "GET", "/eapi/user/profile", None)
    result = decode_json(body, "EAPI profile")
    if not isinstance(result, dict):
        raise ZlibError("zlibrary: invalid EAPI profile response: expected an object")
    if result.get("success") != 1:
        raise ZlibError(
            f"zlibrary: EAPI profile failed: {_rejection(result, 'profile request was rejected')}"
        )
    user = result.get("user")
    if not isinstance(user, dict):
        raise ZlibError("zlibrary: EAPI profile response is missing user")

    today_raw = user.get("downloads_today")
    if today_raw is None:
        today_raw = user.get("dailyDownloadsCount")
    limit_raw = user.get("downloads_limit")
    if limit_raw is None:
        limit_raw = user.get("dailyDownloadLimit")
    daily = eapi_int(today_raw)
    allowed = eapi_int(limit_raw)
    remaining = max(allowed - daily, 0)

    personal = user.get("personalDomains")
    personal_domains = [item for item in personal if isinstance(item, str)] if isinstance(personal, list) else []

    return UserProfile(
        download_limit=DownloadLimit(
            daily_amount=daily,
            daily_allowed=allowed,
            daily_remaining=remaining,
        ),
        id=eapi_string(user.get("id")),
        name=_string(user.get("name")),
        email=_string(user.get("email")),
        kindle_email=_string(user.get("kindle_email")),
        premium=eapi_flag(user.get("isPremium")),
        confirmed=eapi_flag(user.get("confirmed")),
        donations_active=eapi_flag(user.get("donations_active")),
        donations_expire=_string(user.get("donations_expire")),
        personal_domains=personal_domains,
        quota_known=limit_raw is not None,
    )


def download_history(client: Client, page: int) -> DownloadHistoryResult:
    body = eapi_request(
        client, "GET", "/eapi/user/book/downloaded", [("page", page), ("limit", 50)]
    )
    result = decode_json(body, "EAPI history")
    if not isinstance(result, dict):
        raise ZlibError("zlibrary: invalid EAPI history response: expected an object")
    if result.get("success") != 1:
        raise ZlibError(
            f"zlibrary: EAPI history failed: {_rejection(result, 'history request was rejected')}"
        )
    items: list[DownloadHistoryItem] = []
    for raw in _books_field(result, "history"):
        book = map_eapi_book(client, raw)
        date = raw.get("date")
        if not isinstance(date, str) or not date:
            alt = raw.get("downloaded_at")
            date = alt if isinstance(alt, str) else ""
        items.append(
            DownloadHistoryItem(
                id=book.id,
                hash=book.hash,
                name=book.name,
                authors=book.authors,
                url=book.url,
                download_url=book.download_url,
                extension=book.extension,
                size=book.size,
                date=date,
            )
        )
    current, total = _pagination(result, page)
    return DownloadHistoryResult(items=items, page=current, total_pages=total)


def delete_download_history(client: Client, ref: str) -> None:
    identifier = (ref or "").strip().split(":", 1)[0]
    if not identifier or not identifier.isdigit():
        raise ZlibError("zlibrary: history deletion requires a numeric book ID")
    body = eapi_request(client, "GET", f"/eapi/user/book/{identifier}/delete", None)
    result = decode_json(body, "history deletion")
    if not isinstance(result, dict):
        raise ZlibError("zlibrary: invalid history deletion response: expected an object")
    if result.get("success") != 1:
        raise ZlibError(f"zlibrary: history deletion rejected: {_string(result.get('error'))}")


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""
