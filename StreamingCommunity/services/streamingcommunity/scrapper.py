# 22.06.26 - Rewritten for streaming-community.fans (vixsrc.to probing)

import logging
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs


# Internal utilities
from StreamingCommunity.utils.http_client import create_client, get_userAgent
from StreamingCommunity.services._base.object import SeasonManager, Episode, Season


# Variable
headers = {'user-agent': get_userAgent()}
VIXSRC_API = "https://vixsrc.to/api"
MAX_WORKERS = 15


def _get_shared_client():
    return create_client(headers=headers)


class GetSerieInfo:
    def __init__(self, imdb_id: str, series_name: str = None):
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
            logging.error(f"Error fetching {url}: {e}")
        return None

    def _parse_episode_name(self, data: dict) -> str:
        src = data.get('src', '')
        parsed = urlparse(src)
        params = parse_qs(parsed.query)
        d_param = params.get('d', [None])[0]
        if d_param:
            try:
                decoded = base64.b64decode(d_param).decode('utf-8')
                if ' ' in decoded:
                    return decoded.split(' ', 1)[1]
            except Exception:
                pass
        return ""

    def getNumberSeason(self) -> int:
        season = 1
        while season <= 50:
            data = self._get_embed_json(season, 1)
            if data is None:
                break
            self.seasons_manager.add(Season(number=season, name=f"Stagione {season}"))
            season += 1
        return len(self.seasons_manager)

    def _fill_season_episodes(self, season_number: int):
        season = self.seasons_manager.get_season_by_number(season_number)
        if not season or season.episodes.episodes:
            return

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            fut_map = {}
            for ep in range(1, 101):
                fut = executor.submit(self._get_embed_json, season_number, ep)
                fut_map[fut] = ep

            results = []
            for fut in as_completed(fut_map):
                ep_num = fut_map[fut]
                data = fut.result()
                if data is not None:
                    results.append((ep_num, data))

        results.sort(key=lambda x: x[0])
        for ep_num, ep_data in results:
            ep_name = self._parse_episode_name(ep_data) or f"Episodio {ep_num}"
            season.episodes.add(Episode(
                number=ep_num,
                name=ep_name,
                id=f"{self.imdb_id}_{season_number}_{ep_num}"
            ))

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
