# 2026

from typing import List


class Searcher:
    """Unified torrent search across all enabled scrapers."""

    def __init__(self, config_manager): ...

    def search_all(self, query: str, max_seeders: int = 0) -> List: ...
