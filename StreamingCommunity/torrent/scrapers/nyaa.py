# 2026

from StreamingCommunity.torrent.scrapers.base import BaseScraper
from StreamingCommunity.torrent.title_parser import TorrentResult


class NyaaScraper(BaseScraper):
    """Nyaa.si RSS scraper — XML parsing, no Cloudflare."""

    name = "nyaa"
    BASE_URL = "https://nyaa.si"

    def search(self, query: str, **kwargs) -> list: ...
