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

    def is_enabled(self) -> bool:
        return self.config.enabled

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
        retry_count = self.config.scrape_retry_count
        preferred_quality = self.config.preferred_quality

        for name, scraper in self._scrapers.items():
            scraper_results = []
            for attempt in range(retry_count):
                try:
                    log.info("Searching %s for: %s (attempt %d/%d)", name, query, attempt + 1, retry_count)
                    scraper_results = scraper.search(query, limit=limit)
                    log.info("  %s returned %d results", name, len(scraper_results))
                    break
                except Exception as e:
                    log.warning("Scraper %s attempt %d failed: %s", name, attempt + 1, e)
                    if attempt < retry_count - 1:
                        time.sleep(delay)

            results.extend(scraper_results)

            if delay > 0:
                time.sleep(delay)

        results.sort(key=lambda r: r.seeders, reverse=True)

        if max_seeders > 0:
            results = [r for r in results if r.seeders >= max_seeders]

        if preferred_quality and preferred_quality != "best":
            pq = preferred_quality.upper()
            preferred = [r for r in results if pq in (r.quality or "").upper()]
            others = [r for r in results if pq not in (r.quality or "").upper()]
            results = preferred + others

        return results[:limit]
