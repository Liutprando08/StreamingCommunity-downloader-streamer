# 28.08.26
# Scraper for https://musicmp3.ru

from __future__ import annotations

from typing import Any

# External library
from bs4 import BeautifulSoup
from httpx2 import HTTPError

# Internal utilities
from StreamingCommunity.services._base import Entries, EntriesManager, site_constants
from StreamingCommunity.utils.console.shared import console
from StreamingCommunity.utils.http_client import create_client, get_userAgent

STREAM_BASE = "https://listen.musicmp3.ru"


def _get(url: str) -> str:
    """Fetch a musicmp3.ru page and return its HTML."""
    try:
        with create_client(
            headers={
                "User-Agent": get_userAgent(),
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                ),
                "Referer": f"{site_constants.FULL_URL}/",
            }
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text
    except (HTTPError, Exception) as e:
        console.print(f"[red]Error fetching {url}: {e}")
        return ""


def search_songs(query: str) -> EntriesManager:
    """
    Search individual songs and return a manager of track entries.
    """
    manager = EntriesManager()
    search_url = (
        f"{site_constants.FULL_URL}/search.html?text={query.replace(' ', '+')}&all=songs"
    )
    html = _get(search_url)
    if not html:
        return manager

    html = html.replace(
        '<td class="song__artist song__artist--search">Various Artist</td>',
        '<td class="song__artist song__artist--search"><a class="song__link" href="/artist_various-artist.html">Various Artist</a></td>',
    )

    soup = BeautifulSoup(html, "html.parser")
    for row in soup.find_all("tr", class_="song"):
        try:
            play_btn = row.find("a", class_="js_play_btn")
            if play_btn is None or not play_btn.get("rel"):
                continue
            rel_id = play_btn["rel"][0]

            name_el = row.find("td", class_="song__name")
            song = name_el.find("a").get_text(" ", strip=True) if name_el else ""

            artist_el = row.find("td", class_="song__artist")
            artist = (
                artist_el.get_text(" ", strip=True) if artist_el else "Unknown"
            )

            album_el = row.find("td", class_="song__album")
            album = (
                album_el.get_text(" ", strip=True) if album_el else ""
            )

            manager.add(
                Entries(
                    name=song,
                    type="Song",
                    url=f"{STREAM_BASE}/{rel_id}",
                    artist=artist,
                    album=album,
                    rel_id=rel_id,
                )
            )
        except Exception as e:
            console.print(f"[red]Error parsing a song entry: {e}")

    return manager


def search_albums(query: str) -> EntriesManager:
    """
    Search albums and return a manager of album entries.
    """
    manager = EntriesManager()
    search_url = (
        f"{site_constants.FULL_URL}/search.html?text={query.replace(' ', '+')}&all=albums"
    )
    html = _get(search_url)
    if not html:
        return manager

    html = html.replace(
        '<span class="album_report__artist">Various Artists</span>',
        '<a class="album_report__artist" href="/artist_various-artist.html">Various Artist</a>',
    )

    soup = BeautifulSoup(html, "html.parser")
    for el in soup.find_all("a", class_="album_report__link"):
        try:
            url = el.get("href", "")
            name_el = el.find("span", class_="album_report__name")
            album = name_el.get_text(" ", strip=True) if name_el else ""

            artist = "Unknown"
            year = ""
            parent = el.find_parent("div")
            if parent is not None:
                artist_el = parent.find("a", class_="album_report__artist")
                if artist_el is not None:
                    artist = artist_el.get_text(" ", strip=True)
                year_el = parent.find("span", class_="album_report__date")
                if year_el is not None:
                    year = year_el.get_text(" ", strip=True)

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
        except Exception as e:
            console.print(f"[red]Error parsing an album entry: {e}")

    return manager


def search_artists(query: str) -> EntriesManager:
    """
    Search artists and return a manager of artist entries.
    """
    manager = EntriesManager()
    search_url = (
        f"{site_constants.FULL_URL}/search.html?text={query.replace(' ', '+')}&all=artists"
    )
    html = _get(search_url)
    if not html:
        return manager

    soup = BeautifulSoup(html, "html.parser")
    for el in soup.find_all("a", class_="artist_preview__title"):
        try:
            url = el.get("href", "")
            name = el.get_text(" ", strip=True)
            manager.add(
                Entries(
                    name=name,
                    type="Artist",
                    url=f"{site_constants.FULL_URL}{url}",
                )
            )
        except Exception as e:
            console.print(f"[red]Error parsing an artist entry: {e}")

    return manager


def get_albums(artist: Entries) -> EntriesManager:
    """
    Fetch the album list for a given artist entry.
    """
    manager = EntriesManager()
    html = _get(artist.url)
    if not html:
        return manager

    soup = BeautifulSoup(html, "html.parser")
    for el in soup.find_all("a", class_="album_report__link"):
        try:
            url = el.get("href", "")
            name_el = el.find("span", class_="album_report__name")
            album = name_el.get_text(" ", strip=True) if name_el else ""

            year = ""
            parent = el.find_parent("div")
            if parent is not None:
                year_el = parent.find("span", class_="album_report__date")
                if year_el is not None:
                    year = year_el.get_text(" ", strip=True)

            manager.add(
                Entries(
                    name=album,
                    type="Album",
                    url=f"{site_constants.FULL_URL}{url}",
                    artist=artist.name,
                    album=album,
                    year=year,
                )
            )
        except Exception as e:
            console.print(f"[red]Error parsing an album entry: {e}")

    return manager


def get_tracks(album: Entries) -> EntriesManager:
    """
    Fetch the track list for a given album entry.
    """
    manager = EntriesManager()
    html = _get(album.url)
    if not html:
        return manager

    soup = BeautifulSoup(html, "html.parser")
    rows = soup.find_all("tr", itemprop="tracks")
    for row in rows:
        try:
            play_btn = row.find("a", class_="js_play_btn")
            rel_id = play_btn["rel"][0] if play_btn and play_btn.get("rel") else ""

            name_el = row.find("span", itemprop="name")
            track_name = name_el.get_text(" ", strip=True) if name_el else ""

            artist_el = row.find("meta", itemprop="byArtist")
            artist = artist_el["content"] if artist_el else (album.artist or "Unknown")

            album_el = row.find("meta", itemprop="inAlbum")
            album_name = album_el["content"] if album_el else (album.album or album.name)

            if not rel_id:
                continue

            manager.add(
                Entries(
                    name=track_name,
                    type="Song",
                    url=f"{STREAM_BASE}/{rel_id}",
                    artist=artist.replace("&amp;", "and"),
                    album=album_name.replace("&amp;", "and"),
                    rel_id=rel_id,
                )
            )
        except Exception as e:
            console.print(f"[red]Error parsing a track entry: {e}")

    return manager
