# 2026

from StreamingCommunity.torrent.scrapers.base import BaseScraper
from StreamingCommunity.torrent.title_parser import TorrentResult


class Torrent1337Scraper(BaseScraper):
    """1337x scraper — Cloudflare bypassed via curl_cffi impersonation."""

    name = "1337x"
    BASE_URL = "https://1337x.to"

    def search(self, query: str, **kwargs) -> list: ...

    def get_magnet(self, detail_url: str) -> str: ...
