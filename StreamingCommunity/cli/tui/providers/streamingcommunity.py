# StreamingCommunity adapter for the TUI.
# Reuses the existing service functions instead of re-implementing the
# streamingcommunity/vixsrc plumbing.

from __future__ import annotations

from typing import Any

from .base import service_search_lock


class StreamingCommunityProvider:
    name = "Streamingcommunity"
    category = "Film_Serie"
    alias = "streamingcommunity"

    flow = "episode"
    supports_streaming = True
    supports_seasons = True

    _SERIES_TYPES = {"tv", "serie", "ova", "ona", "show"}

    def __init__(self) -> None:
        self._service: Any = None

    def _module(self):
        """Lazy import so TUI startup stays light and CLI stays untouched."""
        if self._service is None:
            import StreamingCommunity.services.streamingcommunity as service

            self._service = service
        return self._service

    def _downloader(self):
        from StreamingCommunity.services.streamingcommunity import downloader

        return downloader

    def search(self, query: str) -> list[Any]:
        service = self._module()
        with service_search_lock(self.alias):
            service.entries_manager.clear()
            service.title_search(query)
            service.entries_manager.sort_by_fuzzy_score(query)
            return list(service.entries_manager.media_list)

    def result_columns(self) -> tuple[tuple[str, str], ...]:
        return (
            ("Nome", "name"),
            ("Tipo", "type"),
            ("Anno", "year"),
            ("ID", "imdb_id"),
        )

    def is_series(self, entry: Any) -> bool:
        return str(getattr(entry, "type", "")).lower() in self._SERIES_TYPES

    def entry_description(self, entry: Any) -> str | None:
        """Return the complete synopsis for ``entry``.

        The archive API truncates ``plot`` to 200 characters, so this reads
        the full text from the title page instead.
        """
        return self._module().get_full_description(entry)

    def new_series_scraper(self, entry: Any) -> Any:
        from StreamingCommunity.services.streamingcommunity.scrapper import (
            GetSerieInfo,
        )

        return GetSerieInfo(entry.imdb_id, entry.name, url=entry.url)

    def seasons(self, scraper: Any) -> list[Any]:
        scraper.getNumberSeason()
        return list(scraper.seasons_manager.seasons)

    def episodes(self, scraper: Any, season_number: int) -> list[Any]:
        return scraper.getEpisodeSeasons(season_number)

    def download_film(self, entry: Any) -> Any:
        return self._downloader().download_film(entry)

    def stream_film(self, entry: Any) -> Any:
        return self._downloader().stream_film(entry)

    def download_episode(
        self, obj_episode: Any, season: int, episode: int, scraper: Any
    ) -> Any:
        return self._downloader().download_episode(
            obj_episode, season, episode, scraper
        )

    def stream_episode(
        self, obj_episode: Any, season: int, episode: int, scraper: Any
    ) -> Any:
        return self._downloader().stream_episode(obj_episode, season, episode, scraper)