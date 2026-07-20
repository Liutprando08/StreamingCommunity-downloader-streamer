# 2026

import logging
import time
from typing import List


# Internal utilities
from StreamingCommunity.torrent.config import TorrentConfig
from StreamingCommunity.torrent.title_parser import TorrentResult


log = logging.getLogger(__name__)


class Searcher:
    """Unified torrent search across all enabled scrapers."""

    def __init__(self, config_manager):
        self.config = TorrentConfig(config_manager)
        self._config_manager = config_manager
        self._scrapers = {}

        from StreamingCommunity.torrent.scrapers import SCRAPERS

        for name, cls in SCRAPERS.items():
            if name == "rutracker":
                continue
            try:
                self._scrapers[name] = cls(config_manager)
                log.debug("Loaded torrent scraper: %s", name)
            except Exception as e:
                log.debug("Failed to load scraper %s: %s", name, e)

    def search_all(
        self,
        query: str,
        max_seeders: int = 0,
        limit: int = 20,
    ) -> List[TorrentResult]:
        """
        Search all enabled scrapers and return aggregated, sorted results.

        Parameters:
            query (str): Search query string.
            max_seeders (int): Minimum seeders threshold. 0 = no filter.
            limit (int): Maximum number of results to return.

        Returns:
            List[TorrentResult]: Results sorted by seeders descending.
        """
        if not query or not query.strip():
            return []

        results: List[TorrentResult] = []
        delay = self.config.scrape_delay_seconds

        for name, scraper in self._scrapers.items():
            try:
                log.info("Searching %s for: %s", name, query)
                scraper_results = scraper.search(query, limit=limit)
                results.extend(scraper_results)
                log.info("  %s returned %d results", name, len(scraper_results))
            except Exception as e:
                log.warning("Scraper %s failed: %s", name, e)
                continue

            if delay > 0:
                time.sleep(delay)

        results.sort(key=lambda r: r.seeders, reverse=True)

        if max_seeders > 0:
            results = [r for r in results if r.seeders >= max_seeders]

        return results[:limit]
