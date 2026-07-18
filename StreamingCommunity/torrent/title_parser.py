# 2026

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TorrentResult:
    """Shared data structure returned by all scrapers."""
    title: str = ""
    quality: str = ""
    size_bytes: int = 0
    seeders: int = 0
    leechers: int = 0
    source: str = ""
    magnet_url: str = ""
    torrent_url: str = ""
    category: str = ""
    tmdb_id: Optional[int] = None
    year: Optional[int] = None
    scraped_at: datetime = field(default_factory=datetime.now)

    @staticmethod
    def safe_arg(value: str) -> str:
        """Prefix values starting with '-' to prevent argument injection in subprocess."""
        if value.startswith("-"):
            return "./" + value
        return value
