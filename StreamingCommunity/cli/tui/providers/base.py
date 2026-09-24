# Contract every service provider must satisfy so the TUI can drive it
# generically. Only StreamingCommunity is implemented for now; other services
# will provide their own adapter and get registered in ``providers/__init__``.

from __future__ import annotations

from typing import Any, Protocol


class ServiceProvider(Protocol):
    name: str
    category: str

    def search(self, query: str) -> list[Any]:
        """Search the provider and return the raw Entries list."""
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

    def download_episode(self, obj_episode: Any, season: int, episode: int, scraper: Any) -> Any:
        """Download a single episode."""
        ...

    def stream_episode(self, obj_episode: Any, season: int, episode: int, scraper: Any) -> Any:
        """Stream a single episode."""
        ...