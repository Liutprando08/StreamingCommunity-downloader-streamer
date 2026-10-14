# Scraper for https://monochrome.st (music)
#
# The site is a SPA; all data comes from a public, auth-free JSON API:
#   https://tracks.monochrome.st
#
# Endpoints used here (reverse engineered from the frontend bundle):
#   GET /search/tracks?q=<query>&limit=<n>   -> tracks
#   GET /search/releases?q=<query>&limit=<n> -> albums / releases
#   GET /search/artists?q=<query>&limit=<n>  -> artists
#   GET /artists/{id}                        -> artist + albums/singles/...
#   GET /releases/{id}                       -> release + tracks
#   GET /track/{id}                          -> the audio stream itself
#
# The stream endpoint returns a plain DRM-free MP4/M4A (AAC) or FLAC file.

from __future__ import annotations

from typing import Any

# External library
from httpx2 import HTTPError

# Internal utilities
from StreamingCommunity.services._base import Entries, EntriesManager
from StreamingCommunity.utils.console.shared import console
from StreamingCommunity.utils.http_client import create_client

# Variables
API_BASE = "https://tracks.monochrome.st"
PAGE_LIMIT = 30

_HEADERS = {
    "Accept": "application/json",
    "Referer": "https://monochrome.st/",
    "Origin": "https://monochrome.st",
}


def _get_json(path: str, params: dict[str, Any] | None = None) -> Any:
    """GET a JSON document from the monochrome tracks API."""
    url = f"{API_BASE}{path}"
    try:
        with create_client(headers=_HEADERS, timeout=30) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except (HTTPError, ValueError) as e:
        console.print(f"[red]monochrome: request failed for {path}: {e}")
        return None


def _artist_names(item: dict) -> str:
    """
    Join the artist names of a track/release.

    Search results expose ``artistNames`` (list of strings) while the release
    detail exposes ``artists`` (list of objects); accept both.
    """
    names = item.get("artistNames")
    if isinstance(names, list):
        joined = ", ".join(str(n) for n in names if n)
        if joined:
            return joined

    artists = item.get("artists")
    if isinstance(artists, list):
        parts: list[str] = []
        for artist in artists:
            if isinstance(artist, dict):
                parts.append(str(artist.get("name") or ""))
            elif isinstance(artist, str):
                parts.append(artist)
        joined = ", ".join(p for p in parts if p)
        if joined:
            return joined

    return "Unknown"


def _track_entry(item: dict, album: str = "", album_artist: str = "") -> Entries:
    """Build a Song entry from a track JSON object."""
    track_id = str(item.get("trackId") or item.get("id") or "")
    artist = _artist_names(item)
    if artist == "Unknown" and album_artist:
        artist = album_artist
    return Entries(
        id=track_id,
        name=item.get("title") or "Unknown",
        type="Song",
        url=f"{API_BASE}/track/{track_id}",
        artist=artist,
        album=album,
        rel_id=track_id,
        track_number=item.get("trackNumber"),
        duration=item.get("duration"),
        image=item.get("artwork"),
    )


def _release_entry(item: dict, artist: str | None = None) -> Entries:
    """Build an Album entry from a release JSON object."""
    release_id = str(item.get("releaseId") or item.get("id") or "")
    title = item.get("title") or "Unknown"
    release_date = str(item.get("releaseDate") or "")
    return Entries(
        id=release_id,
        name=title,
        type="Album",
        url=release_id,
        artist=artist or _artist_names(item),
        album=title,
        year=release_date[:4],
        image=item.get("artwork"),
        rel_id=release_id,
    )


def search_songs(query: str) -> EntriesManager:
    """Search individual tracks."""
    manager = EntriesManager()
    data = _get_json("/search/tracks", {"q": query, "limit": PAGE_LIMIT})
    if not isinstance(data, dict):
        return manager

    for item in data.get("tracks") or []:
        try:
            manager.add(_track_entry(item))
        except Exception as e:
            console.print(f"[red]monochrome: error parsing a track entry: {e}")

    return manager


def search_albums(query: str) -> EntriesManager:
    """Search albums / releases."""
    manager = EntriesManager()
    data = _get_json("/search/releases", {"q": query, "limit": PAGE_LIMIT})
    if not isinstance(data, dict):
        return manager

    for item in data.get("releases") or []:
        try:
            manager.add(_release_entry(item))
        except Exception as e:
            console.print(f"[red]monochrome: error parsing an album entry: {e}")

    return manager


def search_artists(query: str) -> EntriesManager:
    """Search artists."""
    manager = EntriesManager()
    data = _get_json("/search/artists", {"q": query, "limit": PAGE_LIMIT})
    if not isinstance(data, dict):
        return manager

    for item in data.get("artists") or []:
        try:
            artist_id = str(item.get("artistId") or item.get("id") or "")
            name = item.get("name") or item.get("displayName") or "Unknown"
            manager.add(
                Entries(
                    id=artist_id,
                    name=name,
                    type="Artist",
                    url=artist_id,
                    artist=name,
                    desc=item.get("bio") or "",
                    image=item.get("avatar"),
                )
            )
        except Exception as e:
            console.print(f"[red]monochrome: error parsing an artist entry: {e}")

    return manager


def get_albums(artist: Entries) -> EntriesManager:
    """Fetch every release of an artist."""
    manager = EntriesManager()
    artist_id = str(getattr(artist, "id", "") or "")
    data = _get_json(f"/artists/{artist_id}")
    if not isinstance(data, dict):
        return manager

    seen: set[str] = set()
    for key in ("albums", "singles", "compilations", "releases"):
        for item in data.get(key) or []:
            try:
                release_id = str(item.get("releaseId") or item.get("id") or "")
                if not release_id or release_id in seen:
                    continue
                seen.add(release_id)
                manager.add(_release_entry(item, artist=artist.name))
            except Exception as e:
                console.print(f"[red]monochrome: error parsing an album entry: {e}")

    return manager


def get_tracks(album: Entries) -> EntriesManager:
    """Fetch the track list of a release."""
    manager = EntriesManager()
    release_id = str(getattr(album, "rel_id", "") or getattr(album, "id", "") or "")
    if not release_id:
        return manager

    data = _get_json(f"/releases/{release_id}")
    if not isinstance(data, dict):
        return manager

    title = data.get("title") or album.name or ""
    album_artist = _artist_names(data)
    if album_artist == "Unknown":
        album_artist = str(getattr(album, "artist", "") or "")

    for item in data.get("tracks") or []:
        try:
            manager.add(_track_entry(item, album=title, album_artist=album_artist))
        except Exception as e:
            console.print(f"[red]monochrome: error parsing a track entry: {e}")

    return manager
