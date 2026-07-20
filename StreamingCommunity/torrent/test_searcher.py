# 2026
# Standalone test — python StreamingCommunity/torrent/test_searcher.py

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from StreamingCommunity.torrent.title_parser import TorrentResult
from StreamingCommunity.torrent.searcher import Searcher


class _FakeConfig:
    def get_bool(self, section, key, default=None):
        return default if default is not None else False

    def get_int(self, section, key, default=None):
        return default if default is not None else 0

    def get(self, section, key, default=None):
        return default if default is not None else ""


class _FakeConfigManager:
    config = _FakeConfig()


def test_empty_query():
    """Verify empty query returns empty list without calling any scraper."""
    searcher = Searcher(_FakeConfigManager())
    results = searcher.search_all("")
    assert results == [], f"Expected empty list, got {len(results)} results"

    results = searcher.search_all("   ")
    assert results == [], f"Expected empty list for whitespace, got {len(results)} results"
    print("  PASS: empty query returns empty list")


def test_scraper_init():
    """Verify Searcher initializes scrapers from registry."""
    searcher = Searcher(_FakeConfigManager())
    print(f"  Loaded scrapers: {list(searcher._scrapers.keys())}")
    assert "yts" in searcher._scrapers, "YTS scraper not loaded"
    assert "nyaa" in searcher._scrapers, "Nyaa scraper not loaded"
    assert "limetorrent" in searcher._scrapers, "LimeTorrent scraper not loaded"
    assert "torrentgalaxy" in searcher._scrapers, "TorrentGalaxy scraper not loaded"
    assert "rutracker" not in searcher._scrapers, "Rutracker should be skipped"
    print("  PASS: all expected scrapers loaded")


def test_sorting_by_seeders():
    """Verify results are sorted by seeders descending."""
    searcher = Searcher(_FakeConfigManager())

    r1 = TorrentResult(title="A", seeders=10, source="yts")
    r2 = TorrentResult(title="B", seeders=100, source="nyaa")
    r3 = TorrentResult(title="C", seeders=50, source="limetorrent")

    searcher._scrapers = {}
    searcher._scrapers["mock1"] = type("S", (), {"search": staticmethod(lambda q, **kw: [r1])})()
    searcher._scrapers["mock2"] = type("S", (), {"search": staticmethod(lambda q, **kw: [r2])})()
    searcher._scrapers["mock3"] = type("S", (), {"search": staticmethod(lambda q, **kw: [r3])})()

    results = searcher.search_all("test")
    seeders = [r.seeders for r in results]
    assert seeders == sorted(seeders, reverse=True), f"Not sorted: {seeders}"
    print(f"  PASS: results sorted by seeders: {seeders}")


def test_max_seeders_filter():
    """Verify max_seeders threshold filters results."""
    searcher = Searcher(_FakeConfigManager())

    r1 = TorrentResult(title="Low", seeders=5, source="yts")
    r2 = TorrentResult(title="High", seeders=200, source="nyaa")
    r3 = TorrentResult(title="Mid", seeders=50, source="limetorrent")

    searcher._scrapers = {}
    searcher._scrapers["mock1"] = type("S", (), {"search": staticmethod(lambda q, **kw: [r1])})()
    searcher._scrapers["mock2"] = type("S", (), {"search": staticmethod(lambda q, **kw: [r2])})()
    searcher._scrapers["mock3"] = type("S", (), {"search": staticmethod(lambda q, **kw: [r3])})()

    results = searcher.search_all("test", max_seeders=40)
    titles = [r.title for r in results]
    assert "Low" not in titles, "Low seeder result should be filtered"
    assert "High" in titles, "High seeder result should be present"
    assert "Mid" in titles, "Mid seeder result should be present"
    print(f"  PASS: max_seeders filter works: {titles}")


def test_limit():
    """Verify limit is respected."""
    searcher = Searcher(_FakeConfigManager())

    many = [TorrentResult(title=f"T{i}", seeders=100 - i, source="yts") for i in range(30)]

    searcher._scrapers = {}
    searcher._scrapers["mock"] = type("S", (), {"search": staticmethod(lambda q, **kw: many)})()

    results = searcher.search_all("test", limit=5)
    assert len(results) == 5, f"Expected 5, got {len(results)}"
    print(f"  PASS: limit respected: {len(results)} results")


def test_scraper_failure_isolated():
    """Verify one scraper failing doesn't break others."""
    searcher = Searcher(_FakeConfigManager())

    def failing_search(q, **kw):
        raise ConnectionError("network down")

    failing_search = staticmethod(failing_search)

    good_results = [TorrentResult(title="OK", seeders=10, source="yts")]

    searcher._scrapers = {}
    searcher._scrapers["broken"] = type("S", (), {"search": failing_search})()
    searcher._scrapers["good"] = type("S", (), {"search": staticmethod(lambda q, **kw: good_results)})()

    results = searcher.search_all("test")
    assert len(results) == 1, f"Expected 1 result, got {len(results)}"
    assert results[0].title == "OK"
    print("  PASS: scraper failure is isolated")


def test_live_yts_search():
    """Live test against YTS API only (requires network)."""
    try:
        from StreamingCommunity.torrent.scrapers.yts import YtsScraper

        scraper = YtsScraper(_FakeConfigManager())
        results = scraper.search("sintel", limit=5)
        print(f"  Live YTS search returned {len(results)} results")
        for r in results[:3]:
            print(f"    {r.title} | {r.quality} | seeders={r.seeders} | source={r.source}")
        if results:
            print("  PASS: live search returned results")
        else:
            print("  SKIP: live search returned no results (network issue?)")
    except Exception as e:
        print(f"  SKIP: live search failed: {e}")


if __name__ == "__main__":
    test_empty_query()
    test_scraper_init()
    test_sorting_by_seeders()
    test_max_seeders_filter()
    test_limit()
    test_scraper_failure_isolated()
    test_live_yts_search()
    print("\nAll searcher tests passed.")
