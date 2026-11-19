"""Shared constants for the zlib engine.

The values mirror ``internal/zlib/constants.go`` and ``internal/zlib/urls.go``
so a Python caller sends the same requests as the Go CLI.
"""

from __future__ import annotations

from enum import StrEnum

DEFAULT_DOMAIN = "https://z-lib.gd"
TOR_DOMAIN = (
    "http://bookszlibb74ugqojhzhg2a63w5i2atv5bqarulgczawnbmsb6s6qead.onion"
)

ENV_DOMAIN = "ZLIB_DOMAIN"
ENV_PROXY = "ZLIB_PROXY"
ENV_RETRIES = "ZLIB_DOWNLOAD_RETRIES"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT_SECONDS = 180.0
MAX_REDIRECTS = 10

EAPI_LOGIN_PATH = "/eapi/user/login"
EAPI_SEARCH_PATH = "/eapi/book/search"


class Extension(StrEnum):
    TXT = "TXT"
    PDF = "PDF"
    FB2 = "FB2"
    EPUB = "EPUB"
    LIT = "LIT"
    MOBI = "MOBI"
    RTF = "RTF"
    DJV = "DJV"
    DJVU = "DJVU"
    AZW = "AZW"
    AZW3 = "AZW3"


class OrderOption(StrEnum):
    POPULAR = "popular"
    NEWEST = "date_created"
    RECENT = "date_updated"
    BEST_MATCH = "bestmatch"
    DATE = "date"
    TITLE_AZ = "titleA"
    TITLE_ZA = "title"
    YEAR = "year"
    FILE_SIZE_DESC = "filesize"
    FILE_SIZE_ASC = "filesizeA"


class Language(StrEnum):
    ENGLISH = "english"
    CHINESE = "chinese"
    RUSSIAN = "russian"
    FRENCH = "french"
    GERMAN = "german"
    SPANISH = "spanish"
    JAPANESE = "japanese"
    KOREAN = "korean"
    ITALIAN = "italian"
    PORTUGUESE = "portuguese"
    ARABIC = "arabic"
    DUTCH = "dutch"
    POLISH = "polish"
    TURKISH = "turkish"
    HINDI = "hindi"
