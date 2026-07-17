# 2026

from StreamingCommunity.torrent.scrapers.base import BaseScraper
from StreamingCommunity.torrent.title_parser import TorrentResult


class TorrentGalaxyScraper(BaseScraper):
    """TorrentGalaxy scraper — Cloudflare bypassed via curl_cffi impersonation."""

    name = "torrentgalaxy"
    BASE_URL = "https://torrentgalaxy.to"

    def search(self, query: str, **kwargs) -> list: ...
