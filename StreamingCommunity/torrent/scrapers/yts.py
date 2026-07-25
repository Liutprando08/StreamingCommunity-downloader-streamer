# 2026

import logging
import re
from typing import List, Optional

from StreamingCommunity.torrent.scrapers.base import BaseScraper
from StreamingCommunity.torrent.title_parser import TorrentResult
from StreamingCommunity.utils.http_client import create_client_curl


log = logging.getLogger(__name__)

_HASH_RE = re.compile(r'^[a-fA-F0-9]{40}$|^[a-zA-Z2-7]{32}$')


class YtsScraper(BaseScraper):
    """
    YTS API scraper — direct JSON, no Cloudflare.

    Docs: StreamingCommunity/torrent/api.html
    Base URL: https://movies-api.accel.li/api/v2/
    """

    name = "yts"
    BASE_URL = "https://movies-api.accel.li/api/v2"

    def _movie_to_results(self, movie: dict) -> List[TorrentResult]:
        results = []

        for torrent in movie.get("torrents", []):
            info_hash = torrent.get("hash", "")
            if not info_hash or not _HASH_RE.match(info_hash):
                continue

            quality = torrent.get("quality", "")
            torrent_type = torrent.get("type", "")
            type_label = f" {torrent_type}" if torrent_type and torrent_type != "WEB" else ""
            full_quality = f"{quality}{type_label}".strip()

            size_str = torrent.get("size", "")
            size_bytes = self._parse_size(size_str)

            results.append(TorrentResult(
                title=movie.get("title_long", movie.get("title", "")),
                quality=full_quality,
                size_bytes=size_bytes,
                seeders=torrent.get("seeds", 0),
                leechers=torrent.get("peers", 0),
                source="yts",
                magnet_url=self._build_magnet(info_hash, movie.get("title", "")),
                torrent_url=torrent.get("url", ""),
                category="movie",
                year=movie.get("year"),
                tmdb_id=None,
            ))

        return results

    def search(
        self,
        query: str,
        page: int = 1,
        limit: int = 20,
        quality: str = "",
        sort_by: str = "date_added",
        order_by: str = "desc",
        genre: str = "",
        minimum_rating: int = 0,
    ) -> List[TorrentResult]:
        params = {
            "query_term": query,
            "page": page,
            "limit": min(limit, 50),
            "sort_by": sort_by,
            "order_by": order_by,
        }

        if quality:
            params["quality"] = quality
        if genre:
            params["genre"] = genre
        if minimum_rating > 0:
            params["minimum_rating"] = minimum_rating

        try:
            client = create_client_curl(impersonate=self._get_impersonate())
            resp = client.get(f"{self.BASE_URL}/list_movies.json", params=params)
            data = resp.json()
        except Exception as e:
            log.warning("YTS search failed: %s", e)
            return []

        if data.get("status") != "ok":
            log.warning("YTS API returned status: %s", data.get("status_message", "unknown"))
            return []

        movies = data.get("data", {}).get("movies") or []
        results = []
        for movie in movies:
            results.extend(self._movie_to_results(movie))

        return results

    def get_movie_details(self, movie_id: Optional[int] = None, imdb_id: Optional[str] = None) -> Optional[dict]:
        params = {}
        if movie_id:
            params["movie_id"] = movie_id
        if imdb_id:
            params["imdb_id"] = imdb_id

        if not params:
            return None

        try:
            client = create_client_curl(impersonate=self._get_impersonate())
            resp = client.get(f"{self.BASE_URL}/movie_details.json", params=params)
            data = resp.json()
        except Exception as e:
            log.warning("YTS movie_details failed: %s", e)
            return None

        if data.get("status") != "ok":
            return None

        return data.get("data", {}).get("movie")

    def get_suggestions(self, movie_id: int) -> List[dict]:
        try:
            client = create_client_curl(impersonate=self._get_impersonate())
            resp = client.get(
                f"{self.BASE_URL}/movie_suggestions.json",
                params={"movie_id": movie_id},
            )
            data = resp.json()
        except Exception as e:
            log.warning("YTS suggestions failed: %s", e)
            return []

        if data.get("status") != "ok":
            return []

        return data.get("data", {}).get("movies") or []
