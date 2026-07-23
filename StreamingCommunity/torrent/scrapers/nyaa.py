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

_QUALITY_RE = re.compile(
    r"(2160p|1080p|720p|480p|4K|WEB-?DL|WEBRip|HDRip|BluRay|BRRip|DVDRip|HDTV|TELESYNC|CAM|\bTS\b|\bTC\b)",
    re.IGNORECASE,
)

_NS = {"nyaa": "https://nyaa.si/xmlns/nyaa"}

_TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://open.stealth.si:80/announce",
    "udp://open.demonii.com:1337/announce",
]


class NyaaScraper(BaseScraper):
    """Nyaa RSS scraper — XML parsing, no Cloudflare. Base URL from Conf/domains.json."""

    name = "nyaa"

    def __init__(self, config_manager):
        super().__init__(config_manager)
        self.BASE_URL = config_manager.domain.get("nyaa", "full_url", default="https://nyaa.si")
        self.torrent_config = None
        try:
            from StreamingCommunity.torrent.config import TorrentConfig

            self.torrent_config = TorrentConfig(config_manager)
        except Exception:
            pass

    def _get_impersonate(self) -> str:
        if self.torrent_config:
            return self.torrent_config.scrape_impersonate
        return "chrome"

    def _build_magnet(self, info_hash: str, title: str) -> str:
        dn = quote_plus(title)
        tr = "&tr=".join(quote_plus(t) for t in _TRACKERS)
        return f"magnet:?xt=urn:btih:{info_hash}&dn={dn}&tr={tr}"

    def _parse_size(self, size_str: str) -> int:
        normalized = size_str.replace("\xa0", " ").strip()
        parts = normalized.split()
        if len(parts) < 2:
            return 0
        try:
            value = float(parts[0])
            unit = parts[1].upper()
            multipliers = {
                "B": 1,
                "KIB": 1024,
                "MIB": 1024**2,
                "GIB": 1024**3,
                "TIB": 1024**4,
                "KB": 1000,
                "MB": 1000**2,
                "GB": 1000**3,
                "TB": 1000**4,
            }
            return int(value * multipliers.get(unit, 1))
        except (ValueError, IndexError):
            return 0

    def _extract_quality(self, title: str) -> str:
        matches = _QUALITY_RE.findall(title)
        return " ".join(dict.fromkeys(m.upper() for m in matches))

    @staticmethod
    def _extract_year(title: str) -> Optional[int]:
        m = re.search(r"[\(\[\s]?((?:19|20)\d{2})[\)\]\s]?", title)
        return int(m.group(1)) if m else None

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
