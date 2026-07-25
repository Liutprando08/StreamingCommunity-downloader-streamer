# 2026

import logging
import re
import xml.etree.ElementTree as ET
from typing import List, Optional
from urllib.parse import quote_plus

from StreamingCommunity.torrent.scrapers.base import BaseScraper
from StreamingCommunity.torrent.title_parser import TorrentResult
from StreamingCommunity.utils.http_client import create_client_curl


log = logging.getLogger(__name__)

_HASH_RE = re.compile(r"^[a-fA-F0-9]{40}$")

_NS = {"nyaa": "https://nyaa.si/xmlns/nyaa"}


class NyaaScraper(BaseScraper):
    """Nyaa RSS scraper — XML parsing, no Cloudflare. Base URL from Conf/domains.json."""

    name = "nyaa"

    def __init__(self, config_manager):
        super().__init__(config_manager)
        self.BASE_URL = config_manager.domain.get("nyaa", "full_url", default="https://nyaa.si")

    def _item_to_result(self, item: ET.Element) -> Optional[TorrentResult]:
        title_el = item.find("title")
        title = (title_el.text or "").strip() if title_el is not None else ""
        if not title:
            return None

        info_hash_el = item.find("nyaa:infoHash", _NS)
        info_hash = (info_hash_el.text or "").strip() if info_hash_el is not None else ""
        if not info_hash or not _HASH_RE.match(info_hash):
            return None

        link_el = item.find("link")
        torrent_url = (link_el.text or "").strip() if link_el is not None else ""

        seeders_el = item.find("nyaa:seeders", _NS)
        seeders = int(seeders_el.text or "0") if seeders_el is not None else 0

        leechers_el = item.find("nyaa:leechers", _NS)
        leechers = int(leechers_el.text or "0") if leechers_el is not None else 0

        size_el = item.find("nyaa:size", _NS)
        size_str = (size_el.text or "") if size_el is not None else ""
        size_bytes = self._parse_size(size_str)

        category_el = item.find("nyaa:category", _NS)
        category_text = (category_el.text or "").lower() if category_el is not None else ""

        category = "anime"
        if "game" in category_text:
            category = "games"
        elif "music" in category_text:
            category = "music"
        elif "live action" in category_text or "non-" in category_text:
            category = "other"
        elif "picture" in category_text or "art" in category_text:
            category = "other"

        quality = self._extract_quality(title)

        return TorrentResult(
            title=title,
            quality=quality,
            size_bytes=size_bytes,
            seeders=seeders,
            leechers=leechers,
            source="nyaa",
            magnet_url=self._build_magnet(info_hash, title),
            torrent_url=torrent_url,
            category=category,
            year=self._extract_year(title),
            tmdb_id=None,
        )

    def _fetch_rss(self, url: str) -> List[TorrentResult]:
        try:
            client = create_client_curl(impersonate=self._get_impersonate())
            resp = client.get(url)
            xml_data = resp.text
        except Exception as e:
            log.warning("Nyaa RSS request failed: %s", e)
            return []

        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError as e:
            log.warning("Nyaa RSS XML parse error: %s", e)
            return []

        results: List[TorrentResult] = []
        for item in root.findall(".//item"):
            try:
                result = self._item_to_result(item)
                if result:
                    results.append(result)
            except Exception as e:
                log.debug("Nyaa item parse error: %s", e)
                continue

        return results

    def search(
        self,
        query: str,
        page: int = 1,
        limit: int = 20,
        category: str = "",
        **kwargs,
    ) -> List[TorrentResult]:
        params = f"q={quote_plus(query)}&c=0_0&f=0"
        if page > 1:
            params += f"&p={page}"

        url = f"{self.BASE_URL}/?page=rss&{params}"
        results = self._fetch_rss(url)
        return results[:limit] if limit else results

    def search_by_category(
        self,
        category_id: str,
        page: int = 1,
        limit: int = 20,
    ) -> List[TorrentResult]:
        params = f"c={category_id}&f=0"
        if page > 1:
            params += f"&p={page}"

        url = f"{self.BASE_URL}/?page=rss&{params}"
        results = self._fetch_rss(url)
        return results[:limit] if limit else results
