from __future__ import annotations

import html as html_module
import json
import re

# External library
from bs4 import BeautifulSoup
from httpx2 import HTTPError
from rich.prompt import Prompt

from StreamingCommunity.services._base import Entries, EntriesManager, site_constants
from StreamingCommunity.services._base.site_search_manager import (
    base_process_search_result,
    base_search,
)

# Internal utilities
from StreamingCommunity.utils import TVShowManager
from StreamingCommunity.utils.console.shared import console
from StreamingCommunity.utils.domain_check import check_streamingcommunity_domain
from StreamingCommunity.utils.http_client import create_client, get_userAgent

# Logic
from .downloader import download_film, download_series, stream_film, stream_series

# Variable
indice = 0
_useFor = "Film_Serie"
IMDB_RE = re.compile(r"tt(\d+)")

msg = Prompt()
entries_manager = EntriesManager()
table_show_manager = TVShowManager()
_domain_checked = False


def _build_entry(item: dict) -> Entries | None:
    """Build an Entries row from a `/api/v1/web/archive` API item."""
    title_id = item.get("id") or item.get("legacyId")
    slug = item.get("slug")
    if not title_id or not slug:
        return None

    kind = item.get("kind") or ""
    media_type = "tv" if kind == "series" else "film"

    entry = Entries(
        id=int(title_id),
        name=item.get("title") or slug.replace("-", " ").title(),
        type=media_type,
        url=f"{site_constants.FULL_URL}/titles/{title_id}-{slug}-streaming",
        slug=slug,
        year=str(item.get("year") or ""),
        imdb_id=item.get("imdbId") or "",
    )
    entry.size = ""
    entry.score = str(item.get("rating") or "")
    entry.desc = item.get("plot") or ""
    entry.provider_language = ""
    return entry


def _search_archive(query: str) -> int | None:
    """Primary search through the Next.js JSON API.

    Returns the number of results, or None when the API is unavailable so the
    caller can fall back to the legacy HTML scraper.
    """
    search_url = f"{site_constants.FULL_URL}/api/v1/web/archive"
    params = {"q": query, "limit": 30, "count": 1}

    try:
        console.print(f"[cyan]Searching: [yellow]{search_url}")
        response = create_client().get(search_url, params=params)
        response.raise_for_status()
        data = response.json()
    except (HTTPError, ValueError) as e:
        console.print(
            f"[red]Site: {site_constants.SITE_NAME}, archive search error: {e}"
        )
        return None

    items = data.get("items") if isinstance(data, dict) else []
    if items is None:
        # Degraded API response: fall back to the legacy HTML scraper instead
        # of raising (the caller only falls back on a ``None`` return).
        console.print(
            "[yellow]Archive API returned no items, falling back to HTML search"
        )
        return None
    for item in items:
        entry = _build_entry(item)
        if entry:
            entries_manager.add(entry)

    return len(entries_manager)


def _search_legacy_dle(query: str) -> int:
    """Fallback: legacy DLE HTML search page scraping."""
    search_url = f"{site_constants.FULL_URL}/index.php?do=search"
    headers = {
        "user-agent": get_userAgent(),
        "content-type": "application/x-www-form-urlencoded",
    }
    params = {"do": "search", "subaction": "search", "story": query}

    try:
        console.print(f"[cyan]Searching: [yellow]{search_url}")
        response = create_client(headers=headers).get(search_url, params=params)
        response.raise_for_status()
    except HTTPError as e:
        console.print(
            f"[red]Site: {site_constants.SITE_NAME}, request search error: {e}"
        )
        return 0

    soup = BeautifulSoup(response.text, "html.parser")
    tiles = soup.select(".slider-tile")

    if not tiles:
        console.print("[yellow]No results found on search page")
        return 0

    for tile in tiles:
        try:
            link = tile.select_one('a[href*="/titles/"]')
            if not link:
                continue

            href = link.get("href", "")
            if not isinstance(href, str):
                continue
            match = re.search(r"/titles/(\d+)-(.*?)(?:\.html|-streaming)", href)
            if not match:
                continue

            title_id = match.group(1)
            slug = match.group(2)
            title_url = (
                href if href.startswith("http") else f"{site_constants.FULL_URL}{href}"
            )

            name = link.get("data-title") or slug.replace("-", " ").title()
            year = link.get("data-year") or ""
            category = link.get("data-category") or ""
            media_type = "tv" if "Serie TV" in category else "film"

            imdb_id = ""
            img = tile.select_one("img[src*='/uploads/posters/']")
            if img:
                poster_match = re.search(r"/(tt\d+)\.webp", img.get("src", ""))
                if poster_match:
                    imdb_id = poster_match.group(1)

            entry = Entries(
                id=int(title_id),
                name=str(name),
                type=media_type,
                url=title_url,
            )
            entry.size = ""
            entry.score = ""
            entry.desc = ""
            entry.slug = slug
            entry.year = str(year) if year else ""
            entry.provider_language = ""
            entry.imdb_id = imdb_id

            entries_manager.add(entry)
        except HTTPError as e:
            console.print(f"[red]Error parsing search entry: {e}")
            continue

    return len(entries_manager)


def _ensure_domain() -> None:
    """Refresh the StreamingCommunity domain once, before the first search.

    StreamingCommunity changes domain often; scraping the link tracker before
    building the search URL keeps requests on the current domain. Runs once per
    process and never lets a domain-check failure break a search.
    """
    global _domain_checked
    if _domain_checked:
        return
    _domain_checked = True
    try:
        check_streamingcommunity_domain()
    except Exception as e:  # a failed check must not block the search
        console.print(f"[yellow]Domain check skipped: {e}")


def title_search(query: str) -> int:
    _ensure_domain()
    entries_manager.clear()
    table_show_manager.clear()

    count = _search_archive(query)
    if count is not None:
        return count

    return _search_legacy_dle(query)


def process_search_result(select_title, selections=None, scrape_serie=None):
    import os

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


# ── Full synopsis ─────────────────────────────────────────────────────────
#
# The archive API truncates ``plot`` to 200 characters (mid-word), and the
# visible ``<p class="tc-plot">`` on the title page is ellipsised too. The
# untouched TMDB overview the page was built from still lives in the page's
# Next.js flight payload, so we dig it out from there.

_FLIGHT_PUSH_RE = re.compile(
    r'self\.__next_f\.push\(\[1,("(?:\\.|[^"\\])*")\]\)', re.S
)
_PLOT_PARAGRAPH_RE = re.compile(r'<p class="tc-plot">(.*?)</p>', re.S)

# Successful synopsis lookups, keyed by title URL.
_description_cache: dict[str, str] = {}


def _plot_from_payload(payload: str, slug: str) -> str | None:
    """Return the full ``plot`` of the item identified by ``slug``."""
    if not payload or not slug:
        return None
    decoder = json.JSONDecoder()
    for match in re.finditer(re.escape(f'"slug":"{slug}"'), payload):
        key_at = payload.find('"plot":', match.end())
        if key_at == -1:
            continue
        try:
            value, _ = decoder.raw_decode(payload[key_at + len('"plot":') :])
        except ValueError:
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _plot_from_paragraph(page: str) -> str | None:
    """Fallback: the (elliptical) synopsis shown on the title page."""
    match = _PLOT_PARAGRAPH_RE.search(page)
    if not match:
        return None
    text = html_module.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip()
    return text.rstrip("…").strip() or None


def _extract_plot(page: str, slug: str) -> str | None:
    """Extract the full synopsis from a title page, API-truncation-proof."""
    payload = []
    for match in _FLIGHT_PUSH_RE.finditer(page):
        try:
            payload.append(json.loads(match.group(1)))
        except ValueError:
            continue
    return _plot_from_payload("".join(payload), slug) or _plot_from_paragraph(page)


def get_full_description(entry: Entries) -> str | None:
    """Fetch the complete synopsis for ``entry`` from its title page.

    Returns ``None`` when the page has no slug/url or the request/parse
    fails, so callers can keep the (truncated) API description as fallback.
    Successful lookups are cached for the lifetime of the process.
    """
    url = getattr(entry, "url", None)
    slug = getattr(entry, "slug", None)
    if not url or not slug:
        return None
    if url in _description_cache:
        return _description_cache[url]
    try:
        response = create_client().get(url)
        response.raise_for_status()
    except HTTPError:
        return None
    except Exception:
        return None
    description = _extract_plot(response.text or "", slug)
    if description:
        _description_cache[url] = description
    return description

