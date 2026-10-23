# 21.03.25 - AnimeWorld scraper (http_client based)

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from StreamingCommunity.services._base import site_constants
from StreamingCommunity.services._base.object import (
    Episode,
    EpisodeManager,
    Season,
    SeasonManager,
)
from StreamingCommunity.utils import os_manager
from StreamingCommunity.utils.http_client import create_client, get_headers

from .client import get_session_and_csrf

logger = logging.getLogger(__name__)

SINGLE_SEASON = 1


def new_scraper(media_url: str | None = None, site_url: str | None = None) -> "ScrapSerie":
    """Build an AnimeWorld scraper. Uses call-stack to resolve site URL like others."""
    return ScrapSerie(media_url, site_url=site_url)


class ScrapSerie:
    def __init__(self, media_url: str | None = None, site_url: str | None = None):
        self.site_url = str(site_url or site_constants.FULL_URL).rstrip("/")
        self.url = self._absolute_media_url(media_url)
        self.session_id, self.csrf_token = get_session_and_csrf(self.site_url)
        self.client = create_client(
            cookies={"sessionId": self.session_id},
            headers={**get_headers(), "csrf-token": self.csrf_token, "X-Requested-With": "XMLHttpRequest", "Referer": f"{self.site_url}/"},
            timeout=20,
        )

        try:
            self.response = self.client.get(self.url)
            self.response.raise_for_status()
        except Exception as e:
            raise Exception(f"Failed to retrieve anime page: {str(e)}")

        self.soup = BeautifulSoup(self.response.content, "html.parser")
        title_tag = self.soup.find("h1", {"id": "anime-title"})
        if not title_tag:
            title_tag = self.soup.find("h1", class_="title")
        self.series_name = os_manager.get_sanitize_file(
            title_tag.get_text(strip=True) if title_tag is not None else ""
        )

        self.anime_id = None
        player = self.soup.find(id="player")
        if player is not None:
            self.anime_id = str(player.get("data-anime-id") or player.get("data-id") or "")
        if not self.anime_id:
            server = self.soup.find(id="animeId")
            if server is not None:
                self.anime_id = str(server.get("data-id") or "")

        self.is_series = True
        self.movie_year = None
        self.episodes_cache = None
        self._episodes = None
        self.seasons_manager = SeasonManager()
        self.obj_episode_manager = EpisodeManager()

    def _absolute_media_url(self, value: str | None) -> str:
        if not value:
            return self.site_url
        value = str(value).strip()
        if value.startswith(("http://", "https://")):
            return value
        if value.startswith("/"):
            return f"{self.site_url}{value}"
        return f"{self.site_url}/play/{value.lstrip('/')}"

    def get_name(self):
        return self.series_name

    def get_description(self):
        if self.soup is None:
            return None
        meta = self.soup.find("meta", attrs={"name": "description"})
        if meta is not None:
            text = str(meta.get("content") or "").strip()
            if text:
                return text
        return None

    def get_episodes(self, nums=None):
        if self._episodes is None:
            self._episodes = self._parse_episodes()
        self.episodes_cache = self._episodes

        if not nums:
            return list(self._episodes)
        wanted = {str(num) for num in nums}
        return [ep for ep in self._episodes if str(ep.number) in wanted]

    def _parse_episodes(self) -> list[Episode]:
        if self.soup is None:
            return []

        episodes: list[Episode] = []
        seen_ids = set()
        seen_numbers = set()

        anchors = self.soup.select(
            "li.episode > a, li.episode a, a.episode, "
            "a[data-episode-num][href], a[data-episode-id][href], "
            "a[data-id][href*='/play/']"
        )
        for anchor in anchors:
            href = str(anchor.get("href") or "").strip()
            token = anchor.get("data-id")
            episode_id = anchor.get("data-episode-id")
            number = anchor.get("data-episode-num") or anchor.get("data-num")

            if not token and not episode_id and "/play/" in href:
                path = urlparse(href).path.rstrip("/")
                candidate = path.rsplit("/", 1)[-1] if path else ""
                if candidate and candidate != "play":
                    token = candidate

            if not token and not episode_id:
                continue

            if not number:
                match = re.search(r"\d+(?:[.,]\d+)?", anchor.get_text(" ", strip=True))
                if match is not None:
                    number = match.group(0).replace(",", ".")

            key = str(episode_id or token)
            number_key = str(number or episode_id or token)
            if key in seen_ids or number_key in seen_numbers:
                continue
            seen_ids.add(key)
            seen_numbers.add(number_key)

            episodes.append(
                Episode(
                    id=str(token or episode_id),
                    video_id=str(episode_id) if episode_id is not None else None,
                    number=number,
                    name=f"Episodio {number}" if number is not None else "",
                    url=f"{self.site_url}/play/{str(token or episode_id)}" if token else (self.site_url + href if href.startswith('/') else href),
                    episode_id=str(episode_id) if episode_id is not None else None,
                    token=str(token) if token is not None else None,
                )
            )

        if not episodes:
            logger.warning(
                "AnimeWorld returned no episodes for %s (title=%r, episode anchors=%d)",
                self.url,
                self.series_name,
                len(self.soup.select("li.episode, a[data-episode-num], a[data-episode-id]")),
            )

        episodes.sort(key=self._episode_sort_key)
        return episodes

    @staticmethod
    def _episode_sort_key(episode: Episode):
        raw = str(episode.number or "").replace(",", ".")
        try:
            return (0, float(raw), raw)
        except (TypeError, ValueError):
            return (1, 0.0, raw)

    def get_count_episodes(self, season_number: int = SINGLE_SEASON):
        episodes = self.get_episodes()
        return len(episodes) or None

    # GUI/TUI
    def getNumberSeason(self) -> int:
        if len(self.seasons_manager) == 0:
            self.seasons_manager.add(
                Season(
                    id=self.anime_id or self.url,
                    number=SINGLE_SEASON,
                    name=self.series_name or "Stagione 1",
                )
            )
        return SINGLE_SEASON

    def getEpisodeSeasons(self, season_number: int = SINGLE_SEASON):
        return self.get_episodes()

    def get_info_episode(self, index_ep: int, season_number: int = SINGLE_SEASON):
        episodes = self.get_episodes()
        if 0 <= index_ep < len(episodes):
            return episodes[index_ep]
        return None

    def selectEpisode(self, season_number: int = SINGLE_SEASON, episode_index: int = 0):
        return self.get_info_episode(episode_index, season_number)

    def get_entry_description(self):
        return self.get_description()

    def close(self):
        try:
            self.client.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
