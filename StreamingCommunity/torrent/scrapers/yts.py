# 2026

import logging
from typing import List, Optional
from urllib.parse import quote_plus

from StreamingCommunity.torrent.scrapers.base import BaseScraper
from StreamingCommunity.torrent.title_parser import TorrentResult
from StreamingCommunity.utils.http_client import create_client_curl


log = logging.getLogger(__name__)

TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://tracker.dler.org:6969/announce",
    "udp://open.stealth.si:80/announce",
    "udp://open.demonii.com:1337/announce",
    "https://tracker.moeblog.cn:443/announce",
    "udp://open.dstud.io:6969/announce",
    "udp://tracker.srv00.com:6969/announce",
    "https://tracker.zhuqiy.com:443/announce",
    "https://tracker.pmman.tech:443/announce",
]


class YtsScraper(BaseScraper):
    """
    YTS API scraper — direct JSON, no Cloudflare.

    Docs: StreamingCommunity/torrent/api.html
    Base URL: https://movies-api.accel.li/api/v2/
    """

    name = "yts"
    BASE_URL = "https://movies-api.accel.li/api/v2"

    def __init__(self, config_manager):
        super().__init__(config_manager)
        self.torrent_config = None
        try:
            from StreamingCommunity.torrent.config import TorrentConfig
            self.torrent_config = TorrentConfig(config_manager)
        except Exception:
            pass

    def _build_magnet(self, info_hash: str, title: str) -> str:
        dn = quote_plus(title)
        tr = "&tr=".join(quote_plus(t) for t in TRACKERS)
        return f"magnet:?xt=urn:btih:{info_hash}&dn={dn}&tr={tr}"

    def _movie_to_results(self, movie: dict) -> List[TorrentResult]:
        results = []

        for torrent in movie.get("torrents", []):
            info_hash = torrent.get("hash", "")
            if not info_hash:
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

    def _parse_size(self, size_str: str) -> int:
        parts = size_str.split()
        if len(parts) < 2:
            return 0
        try:
            value = float(parts[0])
            unit = parts[1].upper()
            multipliers = {
                "B": 1, "KB": 1024, "MB": 1024**2,
                "GB": 1024**3, "TB": 1024**4,
            }
            return int(value * multipliers.get(unit, 1))
        except (ValueError, IndexError):
            return 0

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
            impersonate = "chrome"
            if self.torrent_config:
                impersonate = self.torrent_config.scrape_impersonate

            client = create_client_curl(impersonate=impersonate)
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
            impersonate = "chrome"
            if self.torrent_config:
                impersonate = self.torrent_config.scrape_impersonate

            client = create_client_curl(impersonate=impersonate)
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
            impersonate = "chrome"
            if self.torrent_config:
                impersonate = self.torrent_config.scrape_impersonate

            client = create_client_curl(impersonate=impersonate)
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
