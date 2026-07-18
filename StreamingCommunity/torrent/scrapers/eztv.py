# 2026

from StreamingCommunity.torrent.scrapers.base import BaseScraper
from StreamingCommunity.torrent.title_parser import TorrentResult


class EztvScraper(BaseScraper):
    """EZTV API scraper — direct JSON, no Cloudflare, TV-only."""

    name = "eztv"
    BASE_URL = "https://eztvx.to/api"

    def search(self, query: str, **kwargs) -> list: ...

    def get_by_imdb(self, imdb_id: str, **kwargs) -> list: ...
