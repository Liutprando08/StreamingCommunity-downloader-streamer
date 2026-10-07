# AnimeUnity adapter for the TUI. Wraps the existing ``services/animeunity``
# search/scraper/downloader functions instead of re-implementing the
# AnimeUnity/Vixcloud plumbing.

from __future__ import annotations

from typing import Any


class AnimeunityProvider:
    name = "Animeunity"
    category = "Anime"
    alias = "animeunity"

    flow = "episode"
    supports_streaming = True
    supports_seasons = True

    _SERIES_TYPES = {"tv", "serie", "ova", "ona", "show"}
    _FILM_TYPES = {"film", "movie"}

    def __init__(self) -> None:
        self._service: Any = None

    def _module(self):
        """Lazy import so TUI startup stays light and CLI stays untouched."""
        if self._service is None:
            import StreamingCommunity.services.animeunity as service

            self._service = service
        return self._service

    def _downloader(self):
        from StreamingCommunity.services.animeunity import downloader

        return downloader

    def search(self, query: str) -> list[Any]:
        service = self._module()
        service.entries_manager.clear()
        service.title_search(query)
        service.entries_manager.sort_by_fuzzy_score(query)
        return list(service.entries_manager.media_list)

    def result_columns(self) -> tuple[tuple[str, str], ...]:
        # animeunity entries carry no imdb_id.
        return (
            ("Nome", "name"),
            ("Tipo", "type"),
            ("Anno", "year"),
            ("TMDB", "tmdb_id"),
        )

    def is_series(self, entry: Any) -> bool:
        """AnimeUnity mixes films and shows in the same catalogue.

        Anything that is explicitly a film is a single-video entry; every other
        type (including a missing one) is walked as an episode list.
        """
        media_type = str(getattr(entry, "type", "") or "").lower()
        return media_type not in self._FILM_TYPES

    def new_series_scraper(self, entry: Any) -> Any:
        # ``new_scraper`` resolves the site URL from inside the service package,
        # which ``site_constants`` requires (it inspects the call stack).
        from StreamingCommunity.services.animeunity.scrapper import new_scraper

        media_id = getattr(entry, "id", None)
        series_name = getattr(entry, "slug", None) or getattr(entry, "name", "")
        return new_scraper(media_id, series_name)

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
        return self._downloader().stream_episode(
            obj_episode, season, episode, scraper
        )
