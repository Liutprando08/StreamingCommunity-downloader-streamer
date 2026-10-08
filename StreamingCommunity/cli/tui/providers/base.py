# Contracts every service provider must satisfy so the TUI can drive it
# generically. Providers declare a ``flow`` that tells the TUI which screen
# sequence to use:
#
#   flow = "episode" -> search -> detail -> seasons -> episodes -> queue
#                      (film/series services)
#   flow = "music"   -> search -> [albums] -> tracks -> queue
#                      (music services)
#   flow = "atomic"  -> search -> detail -> queue
#                      (torrent: one result is one indivisible download)
#
# ``supports_streaming`` and ``supports_seasons`` further narrow what the
# detail screen may offer.

from __future__ import annotations

from typing import Any, Protocol


class ServiceProvider(Protocol):
    """Film/series providers driven through the seasons/episodes flow."""

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

    def download_episode(
        self, obj_episode: Any, season: int, episode: int, scraper: Any
    ) -> Any:
        """Download a single episode."""
        ...

    def stream_episode(
        self, obj_episode: Any, season: int, episode: int, scraper: Any
    ) -> Any:
        """Stream a single episode."""
        ...


class MusicProvider(Protocol):
    """
    Music services (musicmp3, goldenmp3).

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


class TorrentProvider(Protocol):
    """
    Torrent search.

    A torrent result is an opaque magnet link, not an episode list, so the
    atomic flow downloads whatever the user picked in one go. ``download_film``
    decides the destination folder from ``is_series(entry)``.
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

