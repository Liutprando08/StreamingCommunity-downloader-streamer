# 2026

import logging
import re
from typing import List

from StreamingCommunity.torrent.scrapers.base import BaseScraper
from StreamingCommunity.torrent.title_parser import TorrentResult
from StreamingCommunity.utils.http_client import create_client_curl
from StreamingCommunity.utils import tmdb_client


log = logging.getLogger(__name__)

_HASH_RE = re.compile(r'^[a-fA-F0-9]{40}$|^[a-zA-Z2-7]{32}$')
_IMDB_RE = re.compile(r'^tt\d{7,}$|^\d{5,}$')


class EztvScraper(BaseScraper):
    """
    EZTV API scraper — direct JSON, no Cloudflare, TV-only.

    Docs: StreamingCommunity/torrent/scrapers/index.html
    Base URL read from Conf/domains.json
    """

    name = "eztv"

    def __init__(self, config_manager):
        super().__init__(config_manager)
        self.BASE_URL = config_manager.domain.get("eztv", "full_url", default="https://eztvx.to/api")

    def _torrent_to_results(self, torrents: list) -> List[TorrentResult]:
        results = []

        for torrent in torrents:
            info_hash = torrent.get("hash", "")
            if not info_hash or not _HASH_RE.match(info_hash):
                continue

            raw_size = torrent.get("size_bytes", 0)
            try:
                size_bytes = int(raw_size)
            except (ValueError, TypeError):
                size_bytes = 0

            results.append(TorrentResult(
                title=torrent.get("title", ""),
                quality="",
                size_bytes=size_bytes,
                seeders=torrent.get("seeds", 0),
                leechers=torrent.get("peers", 0),
                source="eztv",
                magnet_url=torrent.get("magnet_url", ""),
                torrent_url=torrent.get("url", ""),
                category="tv",
                year=None,
                tmdb_id=None,
            ))

        return results

    def _fetch_torrents(self, params: dict) -> List[TorrentResult]:
        try:
            client = create_client_curl(impersonate=self._get_impersonate())
            resp = client.get(f"{self.BASE_URL}/get-torrents", params=params)
            data = resp.json()
        except Exception as e:
            log.warning("EZTV request failed: %s", e)
            return []

        torrents = data.get("torrents") or []
        return self._torrent_to_results(torrents)

    def search(
        self,
        query: str,
        page: int = 1,
        limit: int = 20,
        **kwargs,
    ) -> List[TorrentResult]:
        if not query or not query.strip():
            return []

        imdb_match = _IMDB_RE.match(query.strip())
        if imdb_match:
            return self.get_by_imdb(query.strip(), page=page, limit=limit)

        try:
            tmdb_id = tmdb_client.search_movie(query.strip())
            if tmdb_id:
                details = tmdb_client.get_movie_details(tmdb_id)
                imdb_id = details.get('imdb_id') if details else None
                if imdb_id:
                    return self.get_by_imdb(imdb_id, page=page, limit=limit)
        except Exception as e:
            log.warning("EZTV: TMDB lookup failed for '%s': %s", query, e)

        log.warning("EZTV: could not resolve '%s' to an IMDB ID via TMDB", query)
        return []

    def get_by_imdb(
        self,
        imdb_id: str,
        page: int = 1,
        limit: int = 20,
    ) -> List[TorrentResult]:
        if not imdb_id or not _IMDB_RE.match(imdb_id):
            log.warning("EZTV invalid imdb_id format: %s", imdb_id)
            return []

        params = {
            "imdb_id": imdb_id,
            "limit": min(limit, 100),
            "page": page,
        }
        return self._fetch_torrents(params)
