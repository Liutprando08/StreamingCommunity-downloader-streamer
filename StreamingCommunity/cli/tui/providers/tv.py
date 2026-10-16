# Adapters for the Film/Serie TV services (Raiplay, Discovery+, PlutoTV, the
# "Realtime" cluster, Crunchyroll, ...).
#
# Every one of these services is built on the same shape as
# streamingcommunity/animeunity: ``title_search`` fills the module-level
# ``entries_manager``, the scraper exposes ``getNumberSeason`` /
# ``getEpisodeSeasons`` with a ``seasons_manager``, and
# ``downloader.download_episode(obj_episode, season, episode, scraper)`` picks
# up an individual episode. None of them offer streaming, so the detail screen
# hides the streaming button automatically via ``supports_streaming``.
#
# The only real differences between services are the scraper constructor
# (each site identifies a series with a different handle: URL, path_id, JSON:API
# id, ...) and whether a film downloader exists at all. ``TvProviderBase``
# covers the common plumbing and each concrete provider below only declares its
# identity and how to build its scraper.

from __future__ import annotations

import importlib
from typing import Any

from .base import service_search_lock


class TvProviderBase:
    flow = "episode"
    supports_streaming = False
    supports_seasons = True

    # Set by subclasses: the folder under StreamingCommunity/services/.
    module_name: str = ""

    # Services that ship a ``download_film`` (Raiplay, Mediaset Infinity,
    # Crunchyroll) can surface film entries. The others walk every result as a
    # series, which is what their downloaders actually support.
    _downloads_films = False

    _FILM_TYPES = {"film", "movie"}

    def __init__(self) -> None:
        self._service: Any = None

    def _module(self):
        """Lazy import so TUI startup stays light and CLI stays untouched."""
        if self._service is None:
            self._service = importlib.import_module(
                f"StreamingCommunity.services.{self.module_name}"
            )
        return self._service

    def _downloader(self):
        return importlib.import_module(
            f"StreamingCommunity.services.{self.module_name}.downloader"
        )

    def search(self, query: str) -> list[Any]:
        service = self._module()
        with service_search_lock(self.module_name):
            service.entries_manager.clear()
            service.title_search(query)
            service.entries_manager.sort_by_fuzzy_score(query)
            results = list(service.entries_manager.media_list)
        if not self._downloads_films:
            # These services ship no film downloader, so a movie entry can only
            # lead to an empty seasons screen. Hide them entirely.
            results = [
                entry
                for entry in results
                if str(getattr(entry, "type", "") or "").lower()
                not in self._FILM_TYPES
            ]
        return results

    def result_columns(self) -> tuple[tuple[str, str], ...]:
        return (
            ("Nome", "name"),
            ("Tipo", "type"),
            ("Anno", "year"),
        )

    def is_series(self, entry: Any) -> bool:
        # Services without a film path route every result through seasons.
        if not self._downloads_films:
            return True
        media_type = str(getattr(entry, "type", "") or "").lower()
        return media_type not in self._FILM_TYPES

    def seasons(self, scraper: Any) -> list[Any]:
        scraper.getNumberSeason()
        return list(scraper.seasons_manager.seasons)

    def episodes(self, scraper: Any, season_number: int) -> list[Any]:
        return scraper.getEpisodeSeasons(season_number)

    def download_film(self, entry: Any) -> Any:
        return self._downloader().download_film(entry)

    def stream_film(self, entry: Any) -> None:
        # Never offered: these services have no stream path.
        return None

    def download_episode(
        self, obj_episode: Any, season: int, episode: int, scraper: Any
    ) -> Any:
        return self._downloader().download_episode(
            obj_episode, season, episode, scraper
        )

    def stream_episode(self, *args: Any) -> None:
        return None


class RaiplayProvider(TvProviderBase):
    name = "Raiplay"
    category = "Film_Serie"
    alias = "raiplay"
    module_name = "raiplay"
    _downloads_films = True

    def result_columns(self) -> tuple[tuple[str, str], ...]:
        return (
            ("Nome", "name"),
            ("Tipo", "type"),
            ("Anno", "year"),
            ("Path", "path_id"),
        )

    def new_series_scraper(self, entry: Any) -> Any:
        from StreamingCommunity.services.raiplay.scrapper import GetSerieInfo

        return GetSerieInfo(entry.path_id)


class MediasetInfinityProvider(TvProviderBase):
    name = "Mediaset Infinity"
    category = "Film_Serie"
    alias = "mediasetinfinity"
    module_name = "mediasetinfinity"
    _downloads_films = True

    def new_series_scraper(self, entry: Any) -> Any:
        from StreamingCommunity.services.mediasetinfinity.scrapper import GetSerieInfo

        return GetSerieInfo(entry.url)


class GuardaserieProvider(TvProviderBase):
    name = "Guardaserie"
    category = "Serie"
    alias = "guardaserie"
    module_name = "guardaserie"

    def result_columns(self) -> tuple[tuple[str, str], ...]:
        return (
            ("Nome", "name"),
            ("Tipo", "type"),
        )

    def new_series_scraper(self, entry: Any) -> Any:
        from StreamingCommunity.services.guardaserie.scrapper import GetSerieInfo

        return GetSerieInfo(entry)


class DiscoveryEuProvider(TvProviderBase):
    name = "Discovery EU"
    category = "Film_Serie"
    alias = "discoveryeu"
    module_name = "discoveryeu"

    def new_series_scraper(self, entry: Any) -> Any:
        from StreamingCommunity.services.discoveryeu.scrapper import GetSerieInfo

        return GetSerieInfo(entry.id)


class DiscoveryUsProvider(TvProviderBase):
    name = "Discovery US"
    category = "Film_Serie"
    alias = "discoveryus"
    module_name = "discoveryus"

    def new_series_scraper(self, entry: Any) -> Any:
        from StreamingCommunity.services.discoveryus.scrapper import GetSerieInfo

        # The search entry packs both Discovery handles into ``id`` as
        # "show_id|alternate_id"; the downloader splits them the same way.
        parts = str(getattr(entry, "id", "")).split("|")
        return GetSerieInfo(parts[1], parts[0])


class PlutoTvProvider(TvProviderBase):
    name = "Pluto TV"
    category = "Serie"
    alias = "plutotv"
    module_name = "plutotv"

    def new_series_scraper(self, entry: Any) -> Any:
        from StreamingCommunity.services.plutotv.scrapper import GetSerieInfo

        url = (
            "https://service-vod.clusters.pluto.tv/v4/vod/"
            f"series/{entry.id}/seasons"
        )
        return GetSerieInfo(url)


class RealtimeProvider(TvProviderBase):
    name = "Realtime"
    category = "Serie"
    alias = "realtime"
    module_name = "realtime"

    def new_series_scraper(self, entry: Any) -> Any:
        from StreamingCommunity.services.realtime.scrapper import GetSerieInfo

        return GetSerieInfo(entry.url)


class _RealtimeClusterProvider(TvProviderBase):
    """Base for the sites that clone Realtime's scraper (dmax, nove, ...)."""

    def new_series_scraper(self, entry: Any) -> Any:
        from StreamingCommunity.services.realtime.scrapper import GetSerieInfo

        return GetSerieInfo(entry.url)


class DmaxProvider(_RealtimeClusterProvider):
    name = "Dmax"
    category = "Serie"
    alias = "dmax"
    module_name = "dmax"


class NoveProvider(_RealtimeClusterProvider):
    name = "Nove"
    category = "Serie"
    alias = "nove"
    module_name = "nove"


class FoodNetworkProvider(_RealtimeClusterProvider):
    name = "Food Network"
    category = "Serie"
    alias = "foodnetwork"
    module_name = "foodnetwork"


class HomeGardenTvProvider(_RealtimeClusterProvider):
    name = "Home Garden TV"
    category = "Serie"
    alias = "homegardentv"
    module_name = "homegardentv"


class CrunchyrollProvider(TvProviderBase):
    name = "Crunchyroll"
    category = "Anime"
    alias = "crunchyroll"
    module_name = "crunchyroll"
    _downloads_films = True

    def result_columns(self) -> tuple[tuple[str, str], ...]:
        return (
            ("Nome", "name"),
            ("Tipo", "type"),
        )

    def new_series_scraper(self, entry: Any) -> Any:
        from StreamingCommunity.services.crunchyroll.scrapper import GetSerieInfo

        # The service URL is "https://www.crunchyroll.com/series/{series_id}".
        return GetSerieInfo(getattr(entry, "id", "") or str(entry.url).split("/")[-1])