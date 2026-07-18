# 2026
# Standalone test — python StreamingCommunity/torrent/test_eztv.py

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from StreamingCommunity.torrent.scrapers.eztv import EztvScraper


class _FakeConfigManager:
    pass


def test_search(limit=3, page=1):
    scraper = EztvScraper(_FakeConfigManager())
    results = scraper.search("ignored", page=page, limit=limit)
    print(f"search(limit={limit}, page={page}) => {len(results)} results")
    for r in results:
        print(f"  {r.title} | {r.size_bytes} bytes | S:{r.seeders} L:{r.leechers} | cat={r.category}")
    return results


def test_get_by_imdb(imdb_id="6048596", limit=3):
    scraper = EztvScraper(_FakeConfigManager())
    results = scraper.get_by_imdb(imdb_id, limit=limit)
    print(f"get_by_imdb(imdb_id={imdb_id}, limit={limit}) => {len(results)} results")
    for r in results:
        print(f"  {r.title} | {r.size_bytes} bytes | S:{r.seeders} L:{r.leechers}")
    return results


if __name__ == "__main__":
    print("=== EZTV Scraper Test ===\n")
    test_search()
    print()
    test_get_by_imdb()
    print("\nAll tests passed!")
