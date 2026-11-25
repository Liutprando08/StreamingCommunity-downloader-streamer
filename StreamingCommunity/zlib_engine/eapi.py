"""EAPI request plumbing: login, search, book details and ISBN helpers.

Mirrors ``internal/zlib/eapi.go`` and ``internal/zlib/eapi_book.go``. The EAPI
is Z-Library's mobile JSON API; every request is form-encoded, and credentials
travel both as ``remix-userid``/``remix-userkey`` headers and as cookies.
"""

from __future__ import annotations

import urllib.parse
from typing import Any, Sequence

from .client import Client
from .constants import (
    DEFAULT_USER_AGENT,
    EAPI_LOGIN_PATH,
    EAPI_SEARCH_PATH,
)
from .errors import (
    DownloadFailed,
    HTTPStatusError,
    LoginFailed,
    ParseFailed,
    SessionExpired,
    ZlibError,
    is_eapi_envelope,
    is_session_rejection,
)
from .http_util import is_bot_protection_response
from .model import Book, BookReference, SearchOptions, SearchResult
from .text import loads_clean
from .urls import absolutize_url

__all__ = [
    "login_eapi",
    "search_eapi",
    "fetch_book_eapi",
    "resolve_eapi_file_url",
    "parse_eapi_book_ref",
    "map_eapi_book",
    "normalize_isbn",
    "valid_isbn10",
    "valid_isbn13",
]


def encode_values(values: Sequence[tuple[str, Any]] | dict[str, Any] | None) -> str:
    """Encode like Go's ``url.Values.Encode``: sorted keys, repeated values kept."""
    if not values:
        return ""
    if isinstance(values, dict):
        pairs: list[tuple[str, Any]] = list(values.items())
    else:
        pairs = list(values)
    pairs.sort(key=lambda pair: pair[0])
    encoded: list[tuple[str, str]] = []
    for key, value in pairs:
        if isinstance(value, bool):
            encoded.append((key, "1" if value else "0"))
        elif value is None:
            continue
        else:
            encoded.append((key, str(value)))
    return urllib.parse.urlencode(encoded, doseq=False)


def eapi_request(
    client: Client,
    method: str,
    path: str,
    values: Sequence[tuple[str, Any]] | dict[str, Any] | None = None,
) -> bytes:
    endpoint = client.domain + path
    body: bytes | None = None
    query = encode_values(values)
    if method.upper() == "GET":
        if query:
            endpoint += "?" + query
    elif query:
        body = query.encode("ascii")

    headers = {
        "Accept": "application/json",
        # Search rejects requests without a client source ("Access denied"),
        # credentials or not; the rest of the EAPI does not check it.
        "source": "android",
        "User-Agent": DEFAULT_USER_AGENT,
    }
    if method.upper() != "GET":
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    cookies = client.cookies()
    user_id = cookies.get("remix_userid", "")
    user_key = cookies.get("remix_userkey", "")
    if user_id:
        headers["remix-userid"] = user_id
    if user_key:
        headers["remix-userkey"] = user_key
    if cookies:
        headers["Cookie"] = "; ".join(f"{name}={value}" for name, value in cookies.items())

    status, response_headers, payload, final_url = client._request(
        method.upper(), endpoint, body, headers
    )

    if is_bot_protection_response(status, response_headers, payload):
        from .errors import BotProtectionError

        raise BotProtectionError(status, final_url)

    # A non-2xx EAPI response can still carry {"success":0,"error":"..."}.
    if not 200 <= status < 300 and not is_eapi_envelope(payload):
        raise HTTPStatusError(status, final_url)

    if is_session_rejection(payload, path, bool(user_key)):
        raise SessionExpired("zlibrary: session expired or revoked, log in again")

    return payload


def decode_json(body: bytes, label: str) -> Any:
    try:
        return loads_clean(body)
    except (ValueError, UnicodeError) as exc:
        raise ParseFailed(f"zlibrary: invalid {label} response: {exc}") from exc


def login_eapi(client: Client, email: str, password: str) -> None:
    client.set_mode("eapi")
    try:
        body = eapi_request(
            client,
            "POST",
            EAPI_LOGIN_PATH,
            [("email", email), ("password", password)],
        )
    except ZlibError as exc:
        raise LoginFailed(f"zlibrary: login failed: {exc}") from exc

    result = decode_json(body, "EAPI login")
    if not isinstance(result, dict):
        raise LoginFailed("zlibrary: login failed: EAPI response is not an object")
    if result.get("success") != 1:
        error = result.get("error")
        message = error if isinstance(error, str) and error else "login was rejected"
        raise LoginFailed(
            "zlibrary: login failed: "
            f"{message}; import a Netscape cookie file with `zlib login --cookies` "
            "if this account cannot use EAPI password login"
        )

    user = result.get("user")
    if not isinstance(user, dict):
        raise LoginFailed("zlibrary: login failed: EAPI response is missing user")
    user_id = eapi_string(user.get("id"))
    key = user.get("remix_userkey")
    if not isinstance(key, str) or not key:
        key = user.get("remix_user_key")
    if not isinstance(key, str):
        key = ""
    if not user_id or not key:
        raise LoginFailed("zlibrary: login failed: EAPI response did not contain remix credentials")
    client.set_cookies({"remix_userid": user_id, "remix_userkey": key})


def search_eapi(
    client: Client,
    query: str,
    page: int,
    count: int,
    options: SearchOptions | None,
) -> SearchResult:
    values: list[tuple[str, Any]] = [
        ("message", query),
        ("page", page),
        ("limit", count),
    ]
    if options is not None:
        if options.exact:
            values.append(("e", 1))
        if options.from_year > 0:
            values.append(("yearFrom", options.from_year))
        if options.to_year > 0:
            values.append(("yearTo", options.to_year))
        for language in options.languages:
            values.append(("languages[]", _enum_value(language).lower()))
        for extension in options.extensions:
            values.append(("extensions[]", _enum_value(extension).lower()))
        if options.order:
            values.append(("order", _enum_value(options.order)))

    body = eapi_request(client, "POST", EAPI_SEARCH_PATH, values)
    result = decode_json(body, "EAPI search")
    if not isinstance(result, dict):
        raise ParseFailed("zlibrary: invalid EAPI search response: expected an object")
    if result.get("success") != 1:
        error = result.get("error")
        message = error if isinstance(error, str) and error else "search was rejected"
        raise ZlibError(f"zlibrary: EAPI search failed: {message}")

    raw_books = result.get("books")
    books = [map_eapi_book(client, item) for item in raw_books or [] if isinstance(item, dict)]
    pagination = result.get("pagination") if isinstance(result.get("pagination"), dict) else {}
    current = _as_int(pagination.get("current")) or page
    total = _as_int(pagination.get("total_pages"))
    return SearchResult(books=books, page=current, total_pages=total)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return 0
    return 0


def parse_eapi_book_ref(ref: str) -> BookReference:
    value = (ref or "").strip()
    parts = value.split(":")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ZlibError("zlibrary: EAPI book ID must use id:hash format")
    return BookReference(id=parts[0], hash=parts[1])


def fetch_book_eapi(client: Client, ref: str) -> Book:
    reference = parse_eapi_book_ref(ref)
    path = (
        "/eapi/book/"
        + urllib.parse.quote(reference.id, safe="")
        + "/"
        + urllib.parse.quote(reference.hash, safe="")
    )
    body = eapi_request(client, "GET", path, None)
    result = decode_json(body, "EAPI book")
    if not isinstance(result, dict):
        raise ParseFailed("zlibrary: invalid EAPI book response: expected an object")
    if result.get("success") != 1:
        error = result.get("error")
        message = error if isinstance(error, str) and error else "book request was rejected"
        raise ZlibError(f"zlibrary: EAPI book failed: {message}")
    item = result.get("book")
    if not isinstance(item, dict):
        raise ParseFailed("zlibrary: invalid EAPI book response: missing book")
    item = dict(item)
    if not eapi_string(item.get("id")):
        item["id"] = reference.id
    if not item.get("hash"):
        item["hash"] = reference.hash
    return map_eapi_book(client, item)


def resolve_eapi_file_url(client: Client, raw_url: str) -> str:
    try:
        target = urllib.parse.urlsplit(raw_url)
        base = urllib.parse.urlsplit(client.domain)
    except ValueError:
        return raw_url
    if (
        target.scheme != base.scheme
        or (target.hostname or "").lower() != (base.hostname or "").lower()
        or not target.path.startswith("/eapi/book/")
        or not target.path.endswith("/file")
    ):
        return raw_url

    body = eapi_request(client, "GET", target.path, None)
    result = decode_json(body, "EAPI file")
    if not isinstance(result, dict):
        raise ParseFailed("zlibrary: invalid EAPI file response: expected an object")
    if result.get("success") != 1:
        error = result.get("error")
        message = error if isinstance(error, str) and error else "file request was rejected"
        raise ZlibError(f"zlibrary: EAPI file request failed: {message}")
    file_info = result.get("file") if isinstance(result.get("file"), dict) else {}
    resolved = (
        file_info.get("downloadLink")
        or result.get("downloadLink")
        or result.get("url")
        or result.get("link")
    )
    if not isinstance(resolved, str) or not resolved:
        raise DownloadFailed("zlibrary: download failed: EAPI returned no file link")
    return absolutize_url(client.domain, resolved)


# ----------------------------------------------------------------------
# Response mapping


def eapi_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return format(value, "f").rstrip("0").rstrip(".") if value != int(value) else str(int(value))
    # Objects and arrays are not scalar text; fmt.Sprint would reveal
    # server-chosen keys verbatim.
    return ""


def eapi_int(value: Any) -> int:
    return _as_int(value)


def eapi_flag(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    try:
        return int(eapi_string(value)) != 0
    except ValueError:
        return None


def eapi_category_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [eapi_category_text(item) for item in value]
        return ", ".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in ("name", "title", "path"):
            name = eapi_category_text(value.get(key))
            if name:
                return name
    return ""


def map_eapi_book(client: Client, item: dict[str, Any]) -> Book:
    book_id = eapi_string(item.get("id"))
    isbn = eapi_string(item.get("identifier")) or eapi_string(item.get("isbn"))
    size = item.get("filesizeString")
    if not isinstance(size, str) or not size:
        size = eapi_string(item.get("filesize"))

    book = Book(
        id=book_id,
        hash=item.get("hash") if isinstance(item.get("hash"), str) else "",
        isbn=isbn,
        isbn10=normalize_isbn(eapi_string(item.get("isbn10"))),
        isbn13=normalize_isbn(eapi_string(item.get("isbn13"))),
        url=absolutize_url(client.domain, _string(item.get("href"))),
        cover=_string(item.get("cover")),
        name=_string(item.get("title")),
        publisher=_string(item.get("publisher")),
        year=eapi_string(item.get("year")),
        language=_string(item.get("language")),
        extension=_string(item.get("extension")),
        size=size,
        rating=eapi_string(item.get("interestScore")),
        quality=eapi_string(item.get("qualityScore")),
        description=_string(item.get("description")),
        categories=eapi_category_text(item.get("categories")),
        edition=eapi_string(item.get("edition")),
        pages=eapi_string(item.get("pages")),
    )
    if not book.categories:
        book.categories = eapi_category_text(item.get("category"))
    if not valid_isbn10(book.isbn10):
        book.isbn10 = ""
    if not valid_isbn13(book.isbn13):
        book.isbn13 = ""

    for value in (eapi_string(item.get("identifier")), eapi_string(item.get("isbn"))):
        normalized = normalize_isbn(value)
        if valid_isbn10(normalized) and not book.isbn10:
            book.isbn10 = normalized
        elif valid_isbn13(normalized) and not book.isbn13:
            book.isbn13 = normalized

    if not book.isbn10 and book.isbn13.startswith("978") and valid_isbn13(book.isbn13):
        book.isbn10 = _isbn10_from_core(book.isbn13[3:12])
    if not book.isbn13 and valid_isbn10(book.isbn10):
        book.isbn13 = _isbn13_from_core("978" + book.isbn10[:9])
    if book.pages == "0":
        book.pages = ""

    if book_id and book.hash:
        book.download_url = (
            client.domain
            + "/eapi/book/"
            + urllib.parse.quote(book_id, safe="")
            + "/"
            + urllib.parse.quote(book.hash, safe="")
            + "/file"
        )
    else:
        book.download_url = absolutize_url(client.domain, _string(item.get("dl")))

    author = _string(item.get("author"))
    if author:
        book.authors = [author]
    return book


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def normalize_isbn(value: str) -> str:
    return value.replace("-", "").replace(" ", "").upper()


def valid_isbn10(value: str) -> bool:
    if len(value) != 10:
        return False
    total = 0
    for index in range(9):
        if not "0" <= value[index] <= "9":
            return False
        total += int(value[index]) * (10 - index)
    check = value[9]
    if check == "X":
        total += 10
    elif "0" <= check <= "9":
        total += int(check)
    else:
        return False
    return total % 11 == 0


def valid_isbn13(value: str) -> bool:
    if len(value) != 13:
        return False
    total = 0
    for index, char in enumerate(value):
        if not "0" <= char <= "9":
            return False
        total += int(char) * (3 if index % 2 else 1)
    return total % 10 == 0


def _isbn10_from_core(core: str) -> str:
    total = sum(int(core[index]) * (10 - index) for index in range(9))
    check = (11 - total % 11) % 11
    return core + ("X" if check == 10 else str(check))


def _isbn13_from_core(core: str) -> str:
    total = sum(int(core[index]) * (3 if index % 2 else 1) for index in range(12))
    return core + str((10 - total % 10) % 10)
