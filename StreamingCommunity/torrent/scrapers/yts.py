# 2026

from StreamingCommunity.torrent.scrapers.base import BaseScraper
from StreamingCommunity.torrent.title_parser import TorrentResult
import requests


class YtsScraper(BaseScraper):
    """YTS API scraper — direct JSON, no Cloudflare."""

    name = "yts"
    BASE_URL = "https://movies-api.accel.li/api/v2/"

    def search(self, query: str, **kwargs) -> list: ...
