# 01.03.24

from __future__ import annotations

import logging

from httpx2 import HTTPError

from StreamingCommunity.services._base import site_constants
from StreamingCommunity.services._base.object import (
    Episode,
    EpisodeManager,
    Season,
    SeasonManager,
)

# Internal utilities
from StreamingCommunity.utils.http_client import create_client_curl, get_headers

logger = logging.getLogger(__name__)

# AnimeUnity serves a single season per title.
SINGLE_SEASON = 1


def new_scraper(media_id=None, series_name=None) -> "ScrapeSerieAnime":
    """
    Build a scraper already bound to the configured site and media.

    Lives here (instead of being inlined by callers) because ``site_constants``
    resolves ``FULL_URL`` by inspecting the call stack for a frame inside
    ``services/animeunity/``. External callers (e.g. the TUI provider) therefore
    have to go through this helper to get a valid URL.
    """
    scrape_serie = ScrapeSerieAnime(site_constants.FULL_URL)
    scrape_serie.setup(None, media_id, series_name)
    return scrape_serie


class ScrapeSerieAnime:
    def __init__(self, url: str):
        """
        Initialize the media scraper for a specific website.

        Args:
            url (str): Url of the streaming site
        """
        self.is_series = False
        self.headers = get_headers()
        self.url = url
        self.episodes_cache = None
        self.seasons_manager: SeasonManager = SeasonManager()
        self.obj_episode_manager: EpisodeManager = EpisodeManager()
        self.series_name = ""
        self.version = None
        self.media_id = None
        self._episodes_by_season: dict[int, list | None] = {}

    def setup(
        self,
        version: str | None = None,
        media_id: int | None = None,
        series_name: str | None = None,
    ):
        self.version = version
        self.media_id = media_id
        self.is_series = series_name is not None
        # Always defined: downloaders read ``series_name`` unconditionally.
        self.series_name = series_name or ""
        self.obj_episode_manager = EpisodeManager()

    def get_count_episodes(self, season_number: int = SINGLE_SEASON) -> int | None:
        """
        Retrieve total number of episodes for the selected media.
        This includes partial episodes (like episode 6.5).

        Returns:
            int: Total episode count including partial episodes
        """
        episodes = self._get_cached_episodes(season_number)
        if episodes:
            return len(episodes)
        return None

    def _get_cached_episodes(self, season_number: int) -> list | None:
        """
        Return the cached episode list of a season, fetching it on first use.
        """
        if season_number not in self._episodes_by_season:
            self._fetch_all_episodes(season_number)

        episodes = self._episodes_by_season.get(season_number)
        # ``episodes_cache`` is kept as an alias of season 1 for compatibility.
        if season_number == SINGLE_SEASON or self.episodes_cache is None:
            self.episodes_cache = episodes
        return episodes

    def _fetch_all_episodes(self, season_number: int = SINGLE_SEASON):
        """
        Fetch all episodes data at once and cache it
        """
        try:
            # Get initial episode count
            response = create_client_curl(headers=self.headers).get(
                f"{self.url}/info_api/{self.media_id}/"
            )
            response.raise_for_status()
            initial_count = response.json()["episodes_count"]

            all_episodes = []
            start_range = 1

            # Fetch episodes in chunks
            while start_range <= initial_count:
                end_range = min(start_range + 119, initial_count)

                params = {"start_range": start_range, "end_range": end_range}

                response = create_client_curl(headers=self.headers).get(
                    f"{self.url}/info_api/{self.media_id}/{season_number}", params=params
                )
                response.raise_for_status()

                chunk_episodes = response.json().get("episodes", [])
                all_episodes.extend(chunk_episodes)
                start_range = end_range + 1

            self._episodes_by_season[season_number] = all_episodes
        except HTTPError as e:
            logger.error(f"Error fetching all episodes: {e}")
            self._episodes_by_season[season_number] = None

    def get_info_episode(
        self, index_ep: int, season_number: int = SINGLE_SEASON
    ) -> Episode | None:
        """
        Get episode info from cache
        """
        episodes = self._get_cached_episodes(season_number)

        if episodes and 0 <= index_ep < len(episodes):
            return _build_episode(episodes[index_ep])
        return None

    # ------------- FOR GUI -------------
    def getNumberSeason(self) -> int:
        """
        Get the total number of seasons available for the anime.
        Note: AnimeUnity doesn't expose seasons, so it is always a single one.
        The season is still registered in ``seasons_manager`` so the generic
        TV/GUI callers can walk it like any other service.
        """
        if len(self.seasons_manager) == 0:
            self.seasons_manager.add(
                Season(
                    id=self.media_id,
                    number=SINGLE_SEASON,
                    name=self.series_name or "Stagione 1",
                )
            )

        return SINGLE_SEASON

    def getEpisodeSeasons(self, season_number: int = SINGLE_SEASON) -> list[Episode]:
        """
        Get all episodes for a specific season.
        """
        episodes = self._get_cached_episodes(season_number)
        return [_build_episode(ep) for ep in episodes or []]

    def selectEpisode(
        self, season_number: int = SINGLE_SEASON, episode_index: int = 0
    ) -> Episode | None:
        """
        Get information for a specific episode.
        """
        return self.get_info_episode(episode_index, season_number)


def _build_episode(raw: dict) -> Episode:
    """
    Map a raw AnimeUnity episode payload to an Episode.
    """
    number = raw.get("number")
    name = raw.get("title") or raw.get("name") or f"Episode {number}"
    return Episode(id=raw.get("id"), number=number, name=name)
