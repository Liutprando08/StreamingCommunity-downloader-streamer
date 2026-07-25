# 2026

import re
import logging
from abc import ABC, abstractmethod
from typing import List, Optional
from urllib.parse import quote_plus


log = logging.getLogger(__name__)

_QUALITY_RE = re.compile(
    r"(2160p|1080p|720p|480p|4K|WEB(?:-?DL|Rip)?|HDRip|BluRay|BRRip|DVDRip|HDTV|TELESYNC|CAM|\bTS\b|\bTC\b)",
    re.IGNORECASE,
)

_TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://open.stealth.si:80/announce",
    "udp://open.demonii.com:1337/announce",
]


class BaseScraper(ABC):
    """Base class for all torrent scrapers with shared utilities."""

    name: str = ""
    BASE_URL: str = ""

    def __init__(self, config_manager):
        self._config_manager = config_manager
        self.torrent_config = None
        self._active_base = ""
        try:
            from StreamingCommunity.torrent.config import TorrentConfig
            self.torrent_config = TorrentConfig(config_manager)
        except Exception:
            pass

    def _get_impersonate(self) -> str:
        if self.torrent_config:
            return self.torrent_config.scrape_impersonate
        return "chrome"

    def _parse_size(self, size_str: str) -> int:
        normalized = size_str.replace("\xa0", " ").replace("\u2009", " ").strip()
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
                "KB": 1024,
                "MB": 1024**2,
                "GB": 1024**3,
                "TB": 1024**4,
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

    @staticmethod
    def _safe_int(text: str) -> int:
        try:
            return int(text.replace(",", ""))
        except (ValueError, TypeError):
            return 0

    def _build_magnet(self, info_hash: str, title: str = "") -> str:
        dn = quote_plus(title) if title else ""
        tr = "&tr=".join(quote_plus(t) for t in _TRACKERS)
        return f"magnet:?xt=urn:btih:{info_hash}&dn={dn}&tr={tr}"

    @abstractmethod
    def search(self, query: str, **kwargs) -> List: ...
