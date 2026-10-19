# Contracts every service provider must satisfy so the TUI can drive it
# generically.
#
# The provider layer exposes exactly four kinds of providers -- VideoProvider,
# MusicProvider, TorrentProvider and MangaProvider -- each configured per
# service. The protocols below describe what a screen may rely on for each
# kind:
#
#   VideoProtocol   flow = "episode" -> search -> detail -> seasons -> episodes -> queue
#                   flow = "atomic"  -> search -> detail -> queue
#                   (film/series/single-video services)
#   MusicProtocol   flow = "music"   -> search -> [albums] -> tracks -> queue
#                   (music services)
#   TorrentProtocol flow = "atomic"  -> search -> detail -> queue
#                   (one result is one indivisible download)
#   MangaProtocol   flow = "episode" -> search -> detail -> volumes -> chapters -> queue
#                   (seasons are volumes, episodes are chapters)
#
# ``supports_streaming`` and ``supports_seasons`` further narrow what the
# detail screen may offer.

from __future__ import annotations

import threading
from typing import Any, Protocol

# Every service keeps a module-level ``EntriesManager`` that ``title_search()``
# clears and repopulates. The home global search and a search screen can hit the
# same service concurrently, so serialise access to that shared manager with one
# lock per service module.
_search_locks: dict[str, threading.Lock] = {}
_search_locks_guard = threading.Lock()


def service_search_lock(module_name: str) -> threading.Lock:
    """Return the per-service lock guarding its shared ``entries_manager``."""
    with _search_locks_guard:
        lock = _search_locks.get(module_name)
        if lock is None:
            lock = threading.Lock()
            _search_locks[module_name] = lock
        return lock


class VideoProtocol(Protocol):
    """Film/series/single-video providers driven through the season flow."""

    name: str
    category: str
    alias: str
    flow: str
    supports_streaming: bool
    supports_seasons: bool

    def search(self, query: str) -> list[Any]:
        """Search the provider and return the raw Entries list."""
        ...

    def result_columns(self) -> tuple[tuple[str, str], ...]:
        """Return (header, entry attribute) pairs for the results table."""
        ...

    def is_series(self, entry: Any) -> bool:
        """Return True when the entry represents a TV series."""
        ...

    def new_series_scraper(self, entry: Any) -> Any:
        """Build a scraper object exposing getNumberSeason/getEpisodeSeasons."""
        ...

    def seasons(self, scraper: Any) -> list[Any]:
        """Return the resolved list of Season objects."""
        ...

    def episodes(self, scraper: Any, season_number: int) -> list[Any]:
        """Return the resolved list of Episode objects for a season."""
        ...

    def download_film(self, entry: Any) -> Any:
        """Download a movie."""
        ...

    def stream_film(self, entry: Any) -> Any:
        """Stream a movie."""
        ...

    def download_episode(self, *args: Any) -> Any:
        """Download a single episode (obj_episode, season, episode, scraper).

        Declared as ``*args`` because the detail/queue screens forward whatever
        the season flow collected, and services without an episode path accept
        the call and return None.
        """
        ...

    def stream_episode(self, *args: Any) -> Any:
        """Stream a single episode (obj_episode, season, episode, scraper)."""
        ...


class MangaProtocol(Protocol):
    """
    Manga providers (mangaworld).

    Same shape as the episode flow, but a "season" is a volume and an
    "episode" is a chapter that the downloader packages into a ``.cbz``.
    They never stream, and ``series_icon``/``series_label`` make the cards
    read "📚 Manga" instead of "📺 Serie".
    """

    name: str
    category: str
    alias: str
    flow: str
    supports_streaming: bool
    supports_seasons: bool

    def search(self, query: str) -> list[Any]:
        """Search the provider and return the raw Entries list."""
        ...

    def result_columns(self) -> tuple[tuple[str, str], ...]:
        """Return (header, entry attribute) pairs for the results table."""
        ...

    def is_series(self, entry: Any) -> bool:
        """Return True: a manga is always walked through volumes/chapters."""
        ...

    def new_series_scraper(self, entry: Any) -> Any:
        """Build the scraper exposing get_volumes/get_chapters_in_volume."""
        ...

    def seasons(self, scraper: Any) -> list[Any]:
        """Return the resolved list of volumes."""
        ...

    def episodes(self, scraper: Any, season_number: int) -> list[Any]:
        """Return the chapters of a volume in ascending order."""
        ...

    def download_film(self, entry: Any) -> Any:
        """Download the whole collection (atomic fallback path)."""
        ...

    def stream_film(self, entry: Any) -> Any:
        """Never offered: manga has no stream path, returns None."""
        ...

    def download_episode(
        self, obj_episode: Any, season: int, episode: int, scraper: Any
    ) -> Any:
        """Download a single chapter."""
        ...

    def stream_episode(
        self, obj_episode: Any, season: int, episode: int, scraper: Any
    ) -> Any:
        """Never offered: manga has no stream path, returns None."""
        ...


class MusicProtocol(Protocol):
    """
    Music services (musicmp3, goldenmp3, monochrome).

    They share the same shape: search by mode (song / album / artist), then
    drill down artist -> album -> tracks before downloading.
    """

    name: str
    category: str
    alias: str
    flow: str
    supports_streaming: bool
    supports_seasons: bool

    def search_modes(self) -> tuple[str, ...]:
        """Return the searchable modes, e.g. ("Song", "Album", "Artist")."""
        ...

    def search(self, query: str, mode: str) -> list[Any]:
        """Search in the given mode and return the raw Entries list."""
        ...

    def result_columns(self) -> tuple[tuple[str, str], ...]:
        """Return (header, entry attribute) pairs for the results table."""
        ...

    def albums(self, entry: Any) -> list[Any]:
        """Return the albums of an artist entry."""
        ...

    def tracks(self, entry: Any) -> list[Any]:
        """Return the tracks of an album entry."""
        ...

    def drilldown(self, entry: Any) -> tuple[str, list[Any]] | None:
        """
        Decide what picking ``entry`` means.

        Return (level, items) where level is "albums" or "tracks", or None
        when the entry is directly downloadable.
        """
        ...

    def download_track(self, entry: Any) -> Any:
        """Download a single track."""
        ...

    def download_album(self, entry: Any) -> Any:
        """Download every track of an album."""
        ...


class TorrentProtocol(Protocol):
    """
    Torrent search.

    A torrent result is an opaque magnet link, not an episode list, so the
    atomic flow downloads whatever the user picked in one go. ``download_film``
    decides the destination folder from ``is_series(entry)``.

    Torrents may optionally gain an Italian audio track taken from
    StreamingCommunity. Providers that support it set ``supports_dub = True``
    and expose ``search_audio_sources`` / ``dub_audio``; the detail screen then
    offers an opt-in switch and the AudioSource screen picks the source.
    """

    name: str
    category: str
    alias: str
    flow: str
    supports_streaming: bool
    supports_seasons: bool

    def search(self, query: str) -> list[Any]:
        """Search every enabled scraper and return the aggregated results."""
        ...

    def result_columns(self) -> tuple[tuple[str, str], ...]:
        """Return (header, entry attribute) pairs for the results table."""
        ...

    def is_series(self, entry: Any) -> bool:
        """Return True when the torrent belongs in the series folder."""
        ...

    def download_film(self, entry: Any) -> Any:
        """Download the whole torrent for ``entry``."""
        ...

    def search_audio_sources(self, query: str) -> list[Any]:
        """Search StreamingCommunity for Italian-audio sources (optional)."""
        ...

    def dub_audio(self, entry: Any, video_path: str, audio_entry: Any) -> Any:
        """Mux an Italian audio source onto ``video_path`` (optional)."""
        ...


# What every screen accepts: the union of the four provider kinds. Screens that
# only care about "some provider" type their constructor with this alias.
AnyProvider = VideoProtocol | MusicProtocol | TorrentProtocol | MangaProtocol

# The kinds that actually walk the season flow. Torrent is atomic and music
# drills down into albums, so only video and manga reach those screens.
SeriesFlowProvider = VideoProtocol | MangaProtocol
