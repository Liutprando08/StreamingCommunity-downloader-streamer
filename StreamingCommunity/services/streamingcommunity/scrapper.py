# 22.06.26 - Rewritten for streaming-community.fans (vixsrc.to probing)

from __future__ import annotations

import base64
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qs, urlparse

from httpx2 import HTTPError

from StreamingCommunity.services._base.object import Episode, Season, SeasonManager

# Internal utilities
from StreamingCommunity.utils.http_client import create_client, get_userAgent

# Variable
headers = {"user-agent": get_userAgent()}
VIXSRC_API = "https://vixsrc.to/api"
MAX_WORKERS = 6
WINDOW_SIZE = 8
MAX_EPISODES = 2000
MAX_SEASONS = 50
STOP_MISSES = 6
logger = logging.getLogger(__name__)


def _get_shared_client():
    return create_client(headers=headers)


class GetSerieInfo:
    def __init__(self, imdb_id: str, series_name: str | None = None):
        self.imdb_id = imdb_id
        self.series_name = series_name or ""
        self.seasons_manager = SeasonManager()
        self._client = _get_shared_client()

    def _get_embed_json(self, season: int, episode: int):
        url = f"{VIXSRC_API}/tv/{self.imdb_id}/{season}/{episode}?lang=it&ref=clone"
        try:
            response = self._client.get(url)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.warning(f"Error fetching {url}: {e}")
        return None

    def _fetch_embed(self, season: int, episode: int):
        """Fetch an embed payload with a single retry for transient failures."""
        data = self._get_embed_json(season, episode)
        if data is None:
            data = self._get_embed_json(season, episode)
        return data

    def _parse_episode_name(self, data: dict) -> str:
        src = data.get("src", "")
        parsed = urlparse(src)
        params = parse_qs(parsed.query)
        d_param = params.get("d", [None])[0]
        if d_param:
            try:
                decoded = base64.b64decode(d_param).decode("utf-8")
                if " " in decoded:
                    return decoded.split(" ", 1)[1]
            except Exception:
                pass
        return ""

    def getNumberSeason(self) -> int:
        season = 1
        consecutive_misses = 0
        while season <= MAX_SEASONS:
            data = self._fetch_embed(season, 1)
            if data is not None:
                consecutive_misses = 0
                self.seasons_manager.add(
                    Season(number=season, name=f"Stagione {season}")
                )
            else:
                consecutive_misses += 1
                if consecutive_misses >= 3:
                    break
            season += 1
        return len(self.seasons_manager)

    def _fill_season_episodes(self, season_number: int):
        season = self.seasons_manager.get_season_by_number(season_number)
        if not season or season.episodes.episodes:
            return

        results: dict[int, dict] = {}
        cursor = 1
        consecutive_misses = 0

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            while cursor <= MAX_EPISODES and consecutive_misses < STOP_MISSES:
                window = list(range(cursor, cursor + WINDOW_SIZE))
                fut_map = {
                    executor.submit(self._fetch_embed, season_number, ep): ep
                    for ep in window
                }

                found: list[int] = []
                missing: list[int] = []
                for fut in as_completed(fut_map):
                    ep_num = fut_map[fut]
                    try:
                        data = fut.result()
                    except Exception:
                        data = None
                    if data is not None:
                        results[ep_num] = data
                        found.append(ep_num)
                    else:
                        missing.append(ep_num)

                # Recover transient misses only when the window produced some
                # hits; a fully empty window means the range genuinely has no
                # episodes and does not deserve a second probe.
                if found:
                    consecutive_misses = 0
                    for ep_num in missing:
                        data = self._fetch_embed(season_number, ep_num)
                        if data is not None:
                            results[ep_num] = data
                            found.append(ep_num)
                else:
                    consecutive_misses += len(window)
                cursor += WINDOW_SIZE

        for ep_num, ep_data in sorted(results.items()):
            ep_name = self._parse_episode_name(ep_data) or f"Episodio {ep_num}"
            season.episodes.add(
                Episode(
                    number=ep_num,
                    name=ep_name,
                    id=f"{self.imdb_id}_{season_number}_{ep_num}",
                )
            )

    def getEpisodeSeasons(self, season_number: int) -> list:
        self._fill_season_episodes(season_number)
        season = self.seasons_manager.get_season_by_number(season_number)
        if not season:
            return []
        return season.episodes.episodes

    def selectEpisode(self, season_number: int, episode_index: int):
        episodes = self.getEpisodeSeasons(season_number)
        if not episodes or episode_index < 0 or episode_index >= len(episodes):
            return None
        return episodes[episode_index]