# 09.11.26 - HD4ME: download-only catalog backed by the theme's cached JSON.
#
# The site is a JavaScript SPA. Its search index is a static file:
#   wp-content/themes/mytheme/cache/posts_data.json
# Cloudflare caches that URL for a year, so the theme appends the value from
# version.json (``?v=...``). Every search downloads the current index; the
# bundled hd4me.json is only an offline fallback.

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from httpx2 import HTTPError

from StreamingCommunity.services._base import Entries, site_constants
from StreamingCommunity.utils.console.shared import console
from StreamingCommunity.utils.http_client import create_client, get_userAgent

# Variable
DEFAULT_BASE_URL = "https://hd4me.net"
INDEX_FILE = Path(__file__).with_name("hd4me.json")
MAX_RESULTS = 200
SIZE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(TB|GB|MB|KB)", re.IGNORECASE)
APOSTROPHE_RE = re.compile(r"['’‘´ʼ＇′ʹ`‛‚]")
HEADERS = {
    "user-agent": get_userAgent(),
    "accept": "application/json, text/plain, */*",
}


def _base_url() -> str:
    """Return the configured HD4ME host, falling back to the built-in one."""
    try:
        configured = site_constants.FULL_URL
    except Exception:
        configured = ""
    return (str(configured or "").strip() or DEFAULT_BASE_URL).rstrip("/")


def _cache_url() -> str:
    return f"{_base_url()}/wp-content/themes/mytheme/cache"


def _get_json(url: str, params: dict | None = None):
    headers = dict(HEADERS)
    headers["referer"] = f"{_base_url()}/"
    with create_client(headers=headers) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        return response.json()


def download_index() -> list[dict]:
    """Download the current search index from HD4ME."""
    cache_url = _cache_url()
    version_payload = _get_json(f"{cache_url}/version.json")
    version = version_payload.get("v") if isinstance(version_payload, dict) else None
    params = {"v": version} if version is not None else None

    payload = _get_json(f"{cache_url}/posts_data.json", params=params)
    if not isinstance(payload, list) or not payload:
        raise ValueError("empty or invalid posts_data.json payload")
    return payload


def load_local_index() -> list[dict]:
    """Load the index bundled with the package (offline fallback)."""
    try:
        with INDEX_FILE.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError) as exc:
        console.print(f"[yellow]HD4ME: bundled index unavailable: {exc}")
        return []

    if not isinstance(payload, list):
        console.print("[yellow]HD4ME: bundled index has an unexpected format")
        return []
    return payload


def get_index() -> list[dict]:
    """Return a fresh index, downloading it on every call.

    The search must always reflect the current catalog, so no in-process cache
    is kept. The bundled JSON is used only when the live download fails.
    """
    console.print(
        f"[cyan]HD4ME: updating index from [yellow]{_cache_url()}/posts_data.json"
    )

    try:
        index = download_index()
    except Exception as exc:  # one failed refresh must not break the search
        console.print(f"[yellow]HD4ME: index download failed: {exc}")
        index = load_local_index()
        if index:
            console.print(
                f"[yellow]HD4ME: using bundled index ({len(index)} titles)"
            )
        return index

    console.print(f"[green]HD4ME: index updated ({len(index)} titles)")
    return index


def _normalize(value) -> str:
    """Case/accent/apostrophe-insensitive text used for matching."""
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return APOSTROPHE_RE.sub("'", text).lower().strip()


def _search_fields(item: dict) -> list[str]:
    fields = [item.get("twy"), item.get("to"), item.get("y")]

    imdb = str(item.get("iid") or "").strip()
    if imdb:
        fields.extend((imdb, imdb if imdb.startswith("tt") else f"tt{imdb}"))

    fields.extend(
        variant.get("t")
        for variant in item.get("tay") or []
        if isinstance(variant, dict)
    )
    return [_normalize(field) for field in fields if field]


def _matches(item: dict, words: list[str]) -> bool:
    fields = _search_fields(item)
    return all(any(word in field for field in fields) for word in words)


def _relevance(item: dict, query: str) -> int:
    """Rank exact and prefix title matches above plain substring hits."""
    titles = [_normalize(item.get("twy")), _normalize(item.get("to"))]
    if any(title == query for title in titles):
        return 0
    if any(title.startswith(query) for title in titles if title):
        return 1
    return 2


def _extract_size(label: str) -> str:
    match = SIZE_RE.search(label or "")
    if not match:
        return ""
    return f"{match.group(1).replace(',', '.')} {match.group(2).upper()}"


def _imdb_id(item: dict) -> str:
    value = str(item.get("iid") or "").strip()
    if not value:
        return ""
    return value if value.startswith("tt") else f"tt{value}"


def _poster_url(item: dict, base_url: str) -> str:
    poster = str(item.get("pa") or "").strip()
    if poster:
        return f"https://image.tmdb.org/t/p/w342/{poster}.jpg"

    imdb = str(item.get("iid") or "").strip()
    if imdb:
        return f"{base_url}/wp-content/uploads/poster/s/{imdb}.webp"
    return ""


def _rating(item: dict) -> str:
    try:
        return f"{float(item.get('rt')):.1f}"
    except (TypeError, ValueError):
        return ""


def _build_entries(item: dict, base_url: str) -> list[Entries]:
    """Expand one index row into one entry per release variant."""
    variants = item.get("tay")
    if not isinstance(variants, list) or not variants:
        variants = [{"t": "", "pid": item.get("pid")}]

    entries: list[Entries] = []
    for variant in variants:
        if not isinstance(variant, dict):
            continue

        pid = variant.get("pid") or item.get("pid")
        if pid is None:
            continue

        label = str(variant.get("t") or "").strip()
        entries.append(
            Entries(
                id=pid,
                name=str(item.get("twy") or item.get("to") or f"Post {pid}"),
                type="film",
                url=f"{base_url}/{pid}",
                size=_extract_size(label),
                year=str(item.get("y") or ""),
                imdb_id=_imdb_id(item),
                desc=label,
                image=_poster_url(item, base_url),
                rating=_rating(item),
            )
        )
    return entries


def search_index(query: str, index: list[dict] | None = None) -> list[Entries]:
    """Search the HD4ME index, expanding each hit into its release variants."""
    query = str(query or "").strip()
    if not query:
        return []

    words = [_normalize(part) for part in query.split() if part.strip()]
    query_norm = _normalize(query)
    data = get_index() if index is None else index

    matches = [
        item
        for item in data
        if isinstance(item, dict) and _matches(item, words)
    ]
    matches.sort(
        key=lambda item: (_relevance(item, query_norm), _normalize(item.get("twy")))
    )

    base_url = _base_url()
    entries: list[Entries] = []
    for item in matches:
        for entry in _build_entries(item, base_url):
            entries.append(entry)
            if len(entries) >= MAX_RESULTS:
                console.print(
                    f"[yellow]HD4ME: more than {MAX_RESULTS} matching releases, "
                    f"showing the first {MAX_RESULTS}"
                )
                return entries
    return entries


def get_post(pid: int | str) -> dict:
    """Fetch the detail JSON for a single post."""
    payload = _get_json(f"{_cache_url()}/posts/{pid}.json")
    if not isinstance(payload, dict):
        raise ValueError(f"invalid post payload for {pid}")
    return payload


def get_download_url(entry: Entries) -> str:
    """Return the MEGA (or other host) URL stored in ``movie.test``."""
    post = get_post(entry.id)
    if post.get("online") is False:
        raise ValueError("post is offline")

    movie = post.get("movie") or {}
    url = str(movie.get("test") or "").strip()
    if not url:
        raise ValueError("post has no download link")
    return url


_description_cache: dict[str, str | None] = {}


def get_full_description(entry: Entries) -> str | None:
    """Return the plot stored in the post detail JSON (cached per process)."""
    key = str(entry.id)
    if key in _description_cache:
        return _description_cache[key]

    try:
        post = get_post(entry.id)
    except HTTPError:
        return None
    except Exception:
        return None

    plot = str((post.get("movie") or {}).get("plot") or "").strip() or None
    _description_cache[key] = plot
    return plot
