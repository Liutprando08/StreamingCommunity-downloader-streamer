# 28.08.26
# Scraper for https://www.goldenmp3.ru

from __future__ import annotations

# External library
from bs4 import BeautifulSoup
from httpx2 import HTTPError

# Internal utilities
from StreamingCommunity.services._base import Entries, EntriesManager, site_constants
from StreamingCommunity.utils.console.shared import console
from StreamingCommunity.utils.http_client import create_client, get_userAgent

STREAM_BASE = "https://listen.musicmp3.ru"


def _get(url: str) -> str:
    """Fetch a goldenmp3.ru page and return its HTML."""
    try:
        with create_client(
            headers={
                "User-Agent": get_userAgent(),
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                ),
                "Referer": f"{site_constants.FULL_URL}/compilations/events/albums",
            }
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text
    except HTTPError as e:
        console.print(f"[red]Error fetching {url}: {e}")
        return ""


def search_albums(query: str) -> EntriesManager:
    """
    Search albums on goldenmp3.ru and return a manager of album entries.
    """
    manager = EntriesManager()
    search_url = f"{site_constants.FULL_URL}/search.html?text={query.replace(' ', '+')}&all=albums"
    html = _get(search_url)
    if not html:
        return manager

    soup = BeautifulSoup(html, "html.parser")
    for li in soup.select("li"):
        dt_a = li.find("dt")
        if dt_a is None:
            continue
        a = dt_a.find("a", href=True)
        if a is None:
            continue
        url = a.get("href", "")
        if url is str and not url.startswith("/"):
            continue

        name_el = a.find("b")
        album = (
            name_el.get_text(" ", strip=True)
            if name_el
            else a.get_text(" ", strip=True)
        )

        artist = "Unknown"
        year = ""
        dd = li.find("dd")
        if dd is not None:
            dd_text = str(dd)
            import re

            # "Studio Album by <a href=...>Artist</a>  released in <year>"
            released_match = re.search(
                r"released\s+in\s+(\d{4})", dd.get_text(" ", strip=True)
            )
            if released_match:
                year = released_match.group(1)

            artist_match = re.search(
                r"Studio\s+Album\s+by\s+<a[^>]*>([^<]+)</a>", dd_text
            ) or re.search(
                r"(?:Compilation|EP|Single)\s+by\s+<a[^>]*>([^<]+)</a>", dd_text
            )
            if artist_match:
                artist = artist_match.group(1).strip()

        manager.add(
            Entries(
                name=album,
                type="Album",
                url=f"{site_constants.FULL_URL}{url}",
                artist=artist,
                album=album,
                year=year,
            )
        )

    return manager


def get_tracks(album: Entries) -> EntriesManager:
    """
    Fetch the track list for a given goldenmp3 album entry.
    """
    manager = EntriesManager()
    if album.url is not None:
        html = _get(album.url)
        if not html:
            return manager

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="title_list")
    rows = table.find_all("tr", itemprop="tracks") if table else []

    for row in rows:
        try:
            play_btn = row.find("a", class_="play")
            rel_id = play_btn["rel"][0] if play_btn and play_btn.get("rel") else ""

            name_el = row.find("span", itemprop="name")
            track_name = name_el.get_text(" ", strip=True) if name_el else ""

            artist = album.artist or "Unknown"

            if not rel_id:
                continue

            manager.add(
                Entries(
                    name=track_name,
                    type="Song",
                    url=f"{STREAM_BASE}/{rel_id}",
                    artist=artist.replace("&amp;", "and"),
                    album=album.album or album.name,
                    rel_id=rel_id,
                )
            )
        except Exception as e:
            console.print(f"[red]Error parsing a track entry: {e}")

    return manager
