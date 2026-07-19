# 2026
# Standalone test — python StreamingCommunity/torrent/test_nyaa.py

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from StreamingCommunity.torrent.scrapers.nyaa import NyaaScraper


class _FakeConfigManager:
    pass


def test_size_parsing():
    """Verify size parsing for binary (GiB/MiB) and decimal (GB/MB) units."""
    scraper = NyaaScraper(_FakeConfigManager())
    cases = [
        ("14.4 GiB", int(14.4 * 1024**3)),
        ("844.0 MiB", int(844.0 * 1024**2)),
        ("29.4 GiB", int(29.4 * 1024**3)),
        ("1.5 GB", int(1.5 * 1000**3)),
        ("500 MB", int(500 * 1000**2)),
        ("", 0),
        ("invalid", 0),
    ]
    for raw, expected in cases:
        got = scraper._parse_size(raw)
        print(f"  '{raw}' => {got} (expected {expected})")
        assert got == expected, f"Size mismatch: got {got}, expected {expected}"
    print("  PASS: all size parses OK")


def test_quality_extraction():
    """Verify quality extraction from titles."""
    scraper = NyaaScraper(_FakeConfigManager())
    cases = [
        ("[Subs] One Piece 1080p BD", "1080P"),
        ("[Team] Naruto 720p WEB-DL", "720P WEB-DL"),
        ("[RG] Bleach 2160p HDRip", "2160P HDRIP"),
        ("[FanSub] Dragon Ball Z 480p DVDRip", "480P DVDRIP"),
        ("No Quality Here", ""),
    ]
    for title, expected in cases:
        got = scraper._extract_quality(title)
        print(f"  '{title}' => '{got}' (expected '{expected}')")
        assert got == expected, f"Quality mismatch: got '{got}', expected '{expected}'"
    print("  PASS: all quality extractions OK")


def test_year_extraction():
    """Verify year extraction from titles."""
    scraper = NyaaScraper(_FakeConfigManager())
    cases = [
        ("One Piece (2024) BD", 2024),
        ("Naruto [2005] 1080p", 2005),
        ("Bleach 2004", 2004),
        ("No Year", None),
    ]
    for title, expected in cases:
        got = scraper._extract_year(title)
        print(f"  '{title}' => {got} (expected {expected})")
        assert got == expected, f"Year mismatch: got {got}, expected {expected}"
    print("  PASS: all year extractions OK")


def test_magnet_building():
    """Verify magnet URL construction from info hash."""
    scraper = NyaaScraper(_FakeConfigManager())
    h = "164ed5647001bf1124acaaac3ed168c56dba3603"
    magnet = scraper._build_magnet(h, "Test Torrent")
    print(f"  magnet: {magnet[:80]}...")
    assert magnet.startswith("magnet:?xt=urn:btih:")
    assert h in magnet
    assert "dn=Test" in magnet
    assert "tr=" in magnet
    print("  PASS: magnet building OK")


def test_search(query="one piece", limit=5):
    """Live RSS search — hits nyaa.si."""
    scraper = NyaaScraper(_FakeConfigManager())
    try:
        results = scraper.search(query, limit=limit)
    except Exception as e:
        print(f"  Network failed: {e}")
        print("  SKIP")
        return []

    print(f"  search('{query}', limit={limit}) => {len(results)} results")
    for r in results[:limit]:
        print(f"    {r.title}")
        print(f"      quality={r.quality} size={r.size_bytes} S:{r.seeders} L:{r.leechers} cat={r.category}")
        print(f"      magnet={r.magnet_url[:60]}...")

    if results:
        first = results[0]
        assert first.source == "nyaa"
        assert first.title, "title must not be empty"
        assert first.magnet_url.startswith("magnet:"), "magnet must start with magnet:"
        assert first.seeders >= 0
        assert first.leechers >= 0
        assert first.size_bytes >= 0
        assert first.torrent_url.startswith("https://nyaa.si/download/")
    print("  PASS: search OK")
    return results


def test_search_by_category(category_id="1_2", limit=3):
    """Live category search (Anime - English-translated)."""
    scraper = NyaaScraper(_FakeConfigManager())
    try:
        results = scraper.search_by_category(category_id, limit=limit)
    except Exception as e:
        print(f"  Network failed: {e}")
        print("  SKIP")
        return []

    print(f"  search_by_category('{category_id}', limit={limit}) => {len(results)} results")
    for r in results:
        print(f"    {r.title} | {r.quality} | S:{r.seeders} L:{r.leechers} | cat={r.category}")

    if results:
        assert results[0].source == "nyaa"
        assert results[0].magnet_url.startswith("magnet:")
    print("  PASS: category search OK")
    return results


if __name__ == "__main__":
    print("=== Nyaa.si Scraper Test ===\n")

    print("[1] Size parsing")
    test_size_parsing()
    print()

    print("[2] Quality extraction")
    test_quality_extraction()
    print()

    print("[3] Year extraction")
    test_year_extraction()
    print()

    print("[4] Magnet building")
    test_magnet_building()
    print()

    print("[5] Live RSS search (network)")
    test_search()
    print()

    print("[6] Live category search (network)")
    test_search_by_category()
    print()

    print("All tests passed!")
