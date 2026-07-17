# 2026

from StreamingCommunity.torrent.scrapers.base import BaseScraper
from StreamingCommunity.torrent.title_parser import TorrentResult


class JackettScraper(BaseScraper):
    """Jackett API scraper — direct JSON, no Cloudflare."""

    name = "jackett"

    def search(self, query: str, **kwargs) -> list: ...
