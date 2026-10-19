# Video providers for the TUI: film/serie catalogs, the "Realtime" cluster,
# Crunchyroll and the single-video services (YouTube, MostraGuarda, Ipersphera).
#
# There is exactly one provider class -- ``VideoProvider`` -- configured per
# service through a ``VideoSpec``. All of these services are built on the same
# shape: ``title_search`` fills the module-level ``entries_manager``, the
# scraper exposes ``getNumberSeason`` / ``getEpisodeSeasons`` with a
# ``seasons_manager`` and ``downloader.download_episode(...)`` picks up an
# individual episode.
#
# What differs per service is only data: the scraper constructor (each site
# identifies a series with a different handle: URL, path_id, JSON:API id, ...),
# the result columns, whether a film downloader exists at all, and whether the
# flow is "episode" (seasons/episodes) or "atomic" (one result = one download).
# That is exactly what a spec row below carries; the class holds the plumbing.

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .base import service_search_lock

DEFAULT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("Nome", "name"),
    ("Tipo", "type"),
    ("Anno", "year"),
)

# The single-video services ship no year on their hits, so they only show the
# title and the media type (YouTube widens its own table below).
ATOMIC_COLUMNS: tuple[tuple[str, str], ...] = (
    ("Nome", "name"),
    ("Tipo", "type"),
)

_SERIES_TYPES = frozenset({"tv", "serie", "ova", "ona", "show"})
_FILM_TYPES = frozenset({"film", "movie"})


# ── series/atomic routing rules ────────────────────────────────────────────
# Which a search hit means for the detail screen. Each spec picks one.
def _always_series(entry: Any) -> bool:
    """Series-only catalogs: every result walks the seasons flow."""
    return True


def _never_series(entry: Any) -> bool:
    """Atomic services: the picked entry is the whole download."""
    return False


def _type_in(types: frozenset[str]) -> Callable[[Any], bool]:
    def test(entry: Any) -> bool:
        return str(getattr(entry, "type", "") or "").lower() in types

    return test


def _type_not_in(types: frozenset[str]) -> Callable[[Any], bool]:
    def test(entry: Any) -> bool:
        return str(getattr(entry, "type", "") or "").lower() not in types

    return test


# ── scraper factories (imports stay inside the body: lazy TUI startup) ─────
def _scraper_streamingcommunity(entry: Any) -> Any:
    from StreamingCommunity.services.streamingcommunity.scrapper import GetSerieInfo

    return GetSerieInfo(entry.imdb_id, entry.name, url=entry.url)


def _description_streamingcommunity(entry: Any) -> str | None:
    # The archive API truncates ``plot`` to 200 characters, so this reads the
    # full text from the title page instead.
    import StreamingCommunity.services.streamingcommunity as service

    return service.get_full_description(entry)


def _scraper_animeunity(entry: Any) -> Any:
    # ``new_scraper`` resolves the site URL from inside the service package,
    # which ``site_constants`` requires (it inspects the call stack).
    from StreamingCommunity.services.animeunity.scrapper import new_scraper

    media_id = getattr(entry, "id", None)
    series_name = getattr(entry, "slug", None) or getattr(entry, "name", "")
    return new_scraper(media_id, series_name)


def _scraper_raiplay(entry: Any) -> Any:
    from StreamingCommunity.services.raiplay.scrapper import GetSerieInfo

    return GetSerieInfo(entry.path_id)


def _scraper_mediaset(entry: Any) -> Any:
    from StreamingCommunity.services.mediasetinfinity.scrapper import GetSerieInfo

    return GetSerieInfo(entry.url)


def _scraper_guardaserie(entry: Any) -> Any:
    from StreamingCommunity.services.guardaserie.scrapper import GetSerieInfo

    return GetSerieInfo(entry)


def _scraper_discoveryeu(entry: Any) -> Any:
    from StreamingCommunity.services.discoveryeu.scrapper import GetSerieInfo

    return GetSerieInfo(entry.id)


def _scraper_discoveryus(entry: Any) -> Any:
    from StreamingCommunity.services.discoveryus.scrapper import GetSerieInfo

    # The search entry packs both Discovery handles into ``id`` as
    # "show_id|alternate_id"; the downloader splits them the same way.
    parts = str(getattr(entry, "id", "")).split("|")
    return GetSerieInfo(parts[1], parts[0])


def _scraper_plutotv(entry: Any) -> Any:
    from StreamingCommunity.services.plutotv.scrapper import GetSerieInfo

    url = (
        "https://service-vod.clusters.pluto.tv/v4/vod/" f"series/{entry.id}/seasons"
    )
    return GetSerieInfo(url)


def _scraper_realtime(entry: Any) -> Any:
    # Also used by the sites that clone Realtime's scraper (dmax, nove, ...).
    from StreamingCommunity.services.realtime.scrapper import GetSerieInfo

    return GetSerieInfo(entry.url)


def _scraper_crunchyroll(entry: Any) -> Any:
    from StreamingCommunity.services.crunchyroll.scrapper import GetSerieInfo

    # The service URL is "https://www.crunchyroll.com/series/{series_id}".
    return GetSerieInfo(getattr(entry, "id", "") or str(entry.url).split("/")[-1])


# ── spec ───────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class VideoSpec:
    """Everything that actually varies between two video services."""

    name: str
    alias: str
    module: str
    category: str = "Film_Serie"
    # "episode" -> seasons/episodes flow, "atomic" -> one result = one download.
    flow: str = "episode"
    # Home tab grouping; None falls back to the category (see sector_of).
    sector: str | None = None
    supports_streaming: bool = False
    supports_seasons: bool = True
    # True when the service ships ``download_film`` and may surface film hits.
    downloads_films: bool = False
    # Services with their own relevance ranking (YouTube) keep it instead of
    # the fuzzy score sort.
    fuzzy_sort: bool = True
    columns: tuple[tuple[str, str], ...] = DEFAULT_COLUMNS
    # What a search hit means for the detail screen. Atomic services must pass
    # ``_never_series`` (as the atomic rows below do) so the detail screen
    # skips the seasons flow and queues the picked entry as a single item.
    series_test: Callable[[Any], bool] = _always_series
    new_scraper: Callable[[Any], Any] | None = None
    description: Callable[[Any], str | None] | None = None


class VideoProvider:
    """One video service, configured by its :class:`VideoSpec`."""

    def __init__(self, spec: VideoSpec) -> None:
        self._spec = spec
        self._service: Any = None

        # Identity and flags are mirrored from the spec so every screen keeps
        # reading them straight off the provider instance.
        self.name = spec.name
        self.alias = spec.alias
        self.category = spec.category
        self.flow = spec.flow
        self.sector = spec.sector
        self.supports_streaming = spec.supports_streaming
        self.supports_seasons = spec.supports_seasons

    # ── lazy service access ───────────────────────────────────────────────
    def _module(self):
        """Lazy import so TUI startup stays light and CLI stays untouched."""
        if self._service is None:
            self._service = importlib.import_module(
                f"StreamingCommunity.services.{self._spec.module}"
            )
        return self._service

    def _downloader(self):
        return importlib.import_module(
            f"StreamingCommunity.services.{self._spec.module}.downloader"
        )

    # ── protocol ──────────────────────────────────────────────────────────
    def search(self, query: str) -> list[Any]:
        spec = self._spec
        service = self._module()
        with service_search_lock(spec.module):
            service.entries_manager.clear()
            service.title_search(query)
            if spec.fuzzy_sort:
                service.entries_manager.sort_by_fuzzy_score(query)
            results = list(service.entries_manager.media_list)

        if spec.flow == "episode" and not spec.downloads_films:
            # These services ship no film downloader, so a movie entry can only
            # lead to an empty seasons screen. Hide them entirely.
            results = [
                entry
                for entry in results
                if str(getattr(entry, "type", "") or "").lower() not in _FILM_TYPES
            ]
        return results

    def result_columns(self) -> tuple[tuple[str, str], ...]:
        return self._spec.columns

    def is_series(self, entry: Any) -> bool:
        return self._spec.series_test(entry)

    def entry_description(self, entry: Any) -> str | None:
        fetch = self._spec.description
        if fetch is None:
            return None
        try:
            return fetch(entry)
        except Exception:
            return None

    def new_series_scraper(self, entry: Any) -> Any:
        factory = self._spec.new_scraper
        if factory is None:
            raise ValueError(f"{self.name} does not expose a series scraper")
        return factory(entry)

    def seasons(self, scraper: Any) -> list[Any]:
        scraper.getNumberSeason()
        return list(scraper.seasons_manager.seasons)

    def episodes(self, scraper: Any, season_number: int) -> list[Any]:
        return scraper.getEpisodeSeasons(season_number)

    def download_film(self, entry: Any) -> Any:
        return self._downloader().download_film(entry)

    def stream_film(self, entry: Any) -> Any:
        # Only the streaming-capable catalogs (streamingcommunity, animeunity)
        # have a stream path; the rest never offer the button.
        if not self._spec.supports_streaming:
            return None
        return self._downloader().stream_film(entry)

    def download_episode(self, *args: Any) -> Any:
        # Atomic services (YouTube, ...) have no episode path at all.
        if self._spec.flow == "atomic":
            return None
        return self._downloader().download_episode(*args)

    def stream_episode(self, *args: Any) -> Any:
        if not self._spec.supports_streaming:
            return None
        return self._downloader().stream_episode(*args)


# ── the video services ─────────────────────────────────────────────────────
# Registration order lives in ``providers/__init__.py`` (the sidebar follows it);
# this table only declares what each service is.
_VIDEO_SPECS: tuple[VideoSpec, ...] = (
    # ── flagship catalogs (streaming allowed) ──────────────────────────────
    VideoSpec(
        name="Streamingcommunity",
        alias="streamingcommunity",
        module="streamingcommunity",
        category="Film_Serie",
        supports_streaming=True,
        downloads_films=True,
        columns=(
            ("Nome", "name"),
            ("Tipo", "type"),
            ("Anno", "year"),
            ("ID", "imdb_id"),
        ),
        series_test=_type_in(_SERIES_TYPES),
        new_scraper=_scraper_streamingcommunity,
        description=_description_streamingcommunity,
    ),
    VideoSpec(
        name="Animeunity",
        alias="animeunity",
        module="animeunity",
        category="Anime",
        supports_streaming=True,
        downloads_films=True,
        columns=(
            ("Nome", "name"),
            ("Tipo", "type"),
            ("Anno", "year"),
            ("TMDB", "tmdb_id"),
        ),
        series_test=_type_not_in(_FILM_TYPES),
        new_scraper=_scraper_animeunity,
    ),
    # ── single-video services (atomic flow) ────────────────────────────────
    VideoSpec(
        name="YouTube",
        alias="youtube",
        module="youtube",
        category="Film_Serie",
        flow="atomic",
        sector="other",
        supports_seasons=False,
        fuzzy_sort=False,
        # ``size`` carries the duration and ``desc`` the channel name.
        columns=(
            ("Nome", "name"),
            ("Tipo", "type"),
            ("Durata", "size"),
            ("Canale", "desc"),
        ),
        series_test=_never_series,
    ),
    VideoSpec(
        name="MostraGuarda",
        alias="mostraguarda",
        module="mostraguarda",
        category="Film",
        flow="atomic",
        sector="other",
        supports_seasons=False,
        fuzzy_sort=False,
        columns=ATOMIC_COLUMNS,
        series_test=_never_series,
    ),
    VideoSpec(
        name="Ipersphera",
        alias="ipersphera",
        module="ipersphera",
        category="Film_Serie",
        flow="atomic",
        sector="other",
        supports_seasons=False,
        fuzzy_sort=False,
        columns=ATOMIC_COLUMNS,
        series_test=_never_series,
    ),
    # ── Film/Serie TV services (episode flow, no streaming) ────────────────
    VideoSpec(
        name="Raiplay",
        alias="raiplay",
        module="raiplay",
        category="Film_Serie",
        downloads_films=True,
        columns=(
            ("Nome", "name"),
            ("Tipo", "type"),
            ("Anno", "year"),
            ("Path", "path_id"),
        ),
        series_test=_type_not_in(_FILM_TYPES),
        new_scraper=_scraper_raiplay,
    ),
    VideoSpec(
        name="Mediaset Infinity",
        alias="mediasetinfinity",
        module="mediasetinfinity",
        category="Film_Serie",
        downloads_films=True,
        series_test=_type_not_in(_FILM_TYPES),
        new_scraper=_scraper_mediaset,
    ),
    VideoSpec(
        name="Guardaserie",
        alias="guardaserie",
        module="guardaserie",
        category="Serie",
        columns=(("Nome", "name"), ("Tipo", "type")),
        new_scraper=_scraper_guardaserie,
    ),
    VideoSpec(
        name="Discovery EU",
        alias="discoveryeu",
        module="discoveryeu",
        category="Film_Serie",
        new_scraper=_scraper_discoveryeu,
    ),
    VideoSpec(
        name="Discovery US",
        alias="discoveryus",
        module="discoveryus",
        category="Film_Serie",
        new_scraper=_scraper_discoveryus,
    ),
    VideoSpec(
        name="Pluto TV",
        alias="plutotv",
        module="plutotv",
        category="Serie",
        new_scraper=_scraper_plutotv,
    ),
    VideoSpec(
        name="Realtime",
        alias="realtime",
        module="realtime",
        category="Serie",
        new_scraper=_scraper_realtime,
    ),
    VideoSpec(
        name="Dmax",
        alias="dmax",
        module="dmax",
        category="Serie",
        new_scraper=_scraper_realtime,
    ),
    VideoSpec(
        name="Nove",
        alias="nove",
        module="nove",
        category="Serie",
        new_scraper=_scraper_realtime,
    ),
    VideoSpec(
        name="Food Network",
        alias="foodnetwork",
        module="foodnetwork",
        category="Serie",
        new_scraper=_scraper_realtime,
    ),
    VideoSpec(
        name="Home Garden TV",
        alias="homegardentv",
        module="homegardentv",
        category="Serie",
        new_scraper=_scraper_realtime,
    ),
    VideoSpec(
        name="Crunchyroll",
        alias="crunchyroll",
        module="crunchyroll",
        category="Anime",
        downloads_films=True,
        columns=(("Nome", "name"), ("Tipo", "type")),
        series_test=_type_not_in(_FILM_TYPES),
        new_scraper=_scraper_crunchyroll,
    ),
)

VIDEO_SPECS: dict[str, VideoSpec] = {spec.alias: spec for spec in _VIDEO_SPECS}
