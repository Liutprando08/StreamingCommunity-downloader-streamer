# 2026

from StreamingCommunity.torrent.scrapers.base import BaseScraper
from StreamingCommunity.torrent.title_parser import TorrentResult


class RutrackerScraper(BaseScraper):
    """RuTracker scraper — login required, Windows-1251 encoding."""

    name = "rutracker"
    BASE_URL = "https://rutracker.net/forum"

    def search(self, query: str, **kwargs) -> list: ...

    def login(self, username: str, password: str) -> bool: ...

    def get_magnet(self, topic_id: int) -> str: ...
