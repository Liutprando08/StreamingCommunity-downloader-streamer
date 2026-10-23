# 21.03.25 - AnimeWorld scraper

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

# Internal utilities
from StreamingCommunity.services._base import site_constants
from StreamingCommunity.services._base.object import (
    Episode,
    EpisodeManager,
    Season,
    SeasonManager,
)
from StreamingCommunity.utils import os_manager

# Logic
from .client import AnimeWorldClient

logger = logging.getLogger(__name__)

SINGLE_SEASON = 1


def new_scraper(
    media_url: str | None = None, site_url: str | None = None
) -> "ScrapSerie":
    """Build an AnimeWorld scraper.

    This helper lives inside the service package on purpose: ``site_constants``
    resolves ``FULL_URL`` by inspecting the call stack for a frame under
    ``services/animeworld/``.  TUI/CLI callers therefore must go through this
    helper rather than constructing ``ScrapSerie`` directly.
    """
    return ScrapSerie(media_url, site_url=site_url)


class ScrapSerie:
    """Scrape an AnimeWorld title and resolve its episode video URLs."""

    def __init__(self, media_url: str | None = None, site_url: str | None = None):
        self.site_url = str(site_url or site_constants.FULL_URL).rstrip("/")
        self.url = self._absolute_media_url(media_url)
        self.client = AnimeWorldClient(self.site_url)
        self.response = None
        self.soup: BeautifulSoup | None = None
        self.series_name = ""
        self.anime_id: str | None = None
        self.is_series = True
        self.movie_year: str | None = None
        self.episodes_cache: list[Episode] | None = None
        self._episodes: list[Episode] | None = None
        self._video_urls: dict[str, str] = {}
        self.seasons_manager = SeasonManager()
        self.obj_episode_manager = EpisodeManager()
        self._load_page()

    # ── setup / page parsing ──────────────────────────────────────────────
    def _absolute_media_url(self, value: str | None) -> str:
        if not value:
            return self.site_url
        value = str(value).strip()
        if value.startswith(("http://", "https://")):
            return value
        if value.startswith("/"):
            return f"{self.site_url}{value}"
        return f"{self.site_url}/play/{value.lstrip('/')}"

    def _load_page(self) -> None:
        try:
            self.response = self.client.get_page(self.url)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load AnimeWorld page {self.url}: {exc}"
            ) from exc

        self.soup = BeautifulSoup(self.response.text, "html.parser")
        title_tag = self.soup.find("h1", {"id": "anime-title"})
        if title_tag is None:
            title_tag = self.soup.find("h1", class_="title")
        self.series_name = os_manager.get_sanitize_file(
            title_tag.get_text(strip=True) if title_tag is not None else ""
        )

        player = self.soup.find(id="player")
        if player is not None:
            self.anime_id = str(player.get("data-anime-id") or player.get("data-id"))
        if not self.anime_id:
            server = self.soup.find(id="animeId")
            if server is not None:
                self.anime_id = str(server.get("data-id"))

    def get_name(self) -> str:
        """Return the sanitized anime title."""
        return self.series_name

    def get_description(self) -> str | None:
        """Return the page description, when present."""
        if self.soup is None:
            return None
        meta = self.soup.find("meta", attrs={"name": "description"})
        if meta is not None:
            text = str(meta.get("content") or "").strip()
            if text:
                return text
        return None

    # ── episodes ──────────────────────────────────────────────────────────
    def get_episodes(self, nums: list[str] | None = None) -> list[Episode]:
        """Return all parsed episodes, sorted by episode number."""
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
        seen_ids: set[str] = set()
        seen_numbers: set[str] = set()

        # The current template is ``li.episode > a`` with ``data-id``, but the
        # site has used more than one wrapper over time.  Keep the fast path
        # first and fall back to any episode-looking anchor so a markup change
        # does not silently produce an empty episode list.
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

            # Older/alternate layouts omit the data attributes; the last path
            # segment of /play/<title>/<token> is the playback token.
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
            # The page can repeat the same episode across paginated ranges.
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
                    url=self.client.absolute_url(href),
                    episode_id=str(episode_id) if episode_id is not None else None,
                    token=str(token) if token is not None else None,
                )
            )

        if not episodes:
            logger.warning(
                "AnimeWorld returned no episodes for %s "
                "(title=%r, episode anchors=%d)",
                self.url,
                self.series_name,
                len(self.soup.select("li.episode, a[data-episode-num], a[data-episode-id]")),
            )

        episodes.sort(key=self._episode_sort_key)
        return episodes

    @staticmethod
    def _episode_sort_key(episode: Episode) -> tuple[int, float, str]:
        raw = str(episode.number or "").replace(",", ".")
        try:
            return (0, float(raw), raw)
        except (TypeError, ValueError):
            return (1, 0.0, raw)

    def get_count_episodes(self, season_number: int = SINGLE_SEASON) -> int | None:
        """Return the number of episodes, or None when the page has none."""
        episodes = self.get_episodes()
        return len(episodes) or None

    # ── video source ──────────────────────────────────────────────────────
    def get_video_url(self, episode: Episode | None) -> str | None:
        """Resolve the direct MP4 URL for an episode.

        AnimeWorld's ``/api/episode/info`` returns a ``grabber`` URL.  Older
        episodes may only expose the player page, so the ``<source>`` tag is
        used as a fallback.
        """
        if episode is None:
            return None

        token = getattr(episode, "token", None) or getattr(episode, "id", None)
        if not token:
            logger.warning("AnimeWorld episode has no token: %r", episode)
            return None

        token = str(token)
        if token in self._video_urls:
            return self._video_urls[token]

        try:
            info = self.client.episode_info(token)
        except Exception as exc:
            logger.warning("AnimeWorld episode info failed for %s: %s", token, exc)
            return None

        url = info.get("grabber")
        if not isinstance(url, str) or not url.strip():
            url = info.get("download")
        if isinstance(url, str) and url.strip():
            self._video_urls[token] = url.strip()
            return self._video_urls[token]

        if info.get("target"):
            try:
                page = self.client.player_page(str(info["target"]))
                fallback = self._extract_source(page.text)
                if fallback:
                    self._video_urls[token] = fallback
                    return self._video_urls[token]
            except Exception as exc:
                logger.warning(
                    "AnimeWorld fallback player failed for %s: %s", token, exc
                )

        logger.warning("AnimeWorld returned no playable URL for %s", token)
        return None

    def _extract_source(self, html: str) -> str | None:
        soup = BeautifulSoup(html, "html.parser")
        source = soup.find("source")
        if source is not None:
            src = source.get("src")
            if src:
                return self.client.absolute_url(str(src).strip())

        video = soup.find("video")
        if video is not None:
            src = video.get("src")
            if src:
                return self.client.absolute_url(str(src).strip())
        return None

    # ── GUI / TUI protocol ────────────────────────────────────────────────
    def getNumberSeason(self) -> int:
        """AnimeWorld exposes one flat episode list, like AnimeUnity."""
        if len(self.seasons_manager) == 0:
            self.seasons_manager.add(
                Season(
                    id=self.anime_id or self.url,
                    number=SINGLE_SEASON,
                    name=self.series_name or "Stagione 1",
                )
            )
        return SINGLE_SEASON

    def getEpisodeSeasons(self, season_number: int = SINGLE_SEASON) -> list[Episode]:
        return self.get_episodes()

    def get_info_episode(
        self, index_ep: int, season_number: int = SINGLE_SEASON
    ) -> Episode | None:
        episodes = self.get_episodes()
        if 0 <= index_ep < len(episodes):
            return episodes[index_ep]
        return None

    def selectEpisode(
        self, season_number: int = SINGLE_SEASON, episode_index: int = 0
    ) -> Episode | None:
        return self.get_info_episode(episode_index, season_number)

    # ── misc ──────────────────────────────────────────────────────────────
    def get_entry_description(self) -> str | None:
        return self.get_description()

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "ScrapSerie":
        return self

    def __exit__(self, *_exc_info) -> None:
        self.close()
