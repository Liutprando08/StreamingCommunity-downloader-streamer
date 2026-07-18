# 2026

from StreamingCommunity.torrent.scrapers.base import BaseScraper
from StreamingCommunity.torrent.title_parser import TorrentResult


class LimeTorrentScraper(BaseScraper):
    """LimeTorrents scraper — curl_cffi Cloudflare bypass, HTML parsing."""

    name = "limetorrent"
    BASE_URL = "https://limetorrents.fun"
    MIRRORS = [
        "https://limetorrents.fun",
        "https://www.limetorrents.pro",
        "https://limetorrents.cc",
    ]

    def search(self, query: str, **kwargs) -> list: ...

    def get_magnet(self, detail_url: str) -> str: ...
