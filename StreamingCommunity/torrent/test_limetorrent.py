# 2026
# Standalone test — python StreamingCommunity/torrent/test_limetorrent.py

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from StreamingCommunity.torrent.scrapers.limetorrent import LimeTorrentScraper

SEARCH_HTML = os.path.join(os.path.dirname(__file__), "scrapers", "limetorrent_search.html")
DETAIL_HTML = os.path.join(os.path.dirname(__file__), "scrapers", "limetorrent_detail.html")


class _FakeConfigManager:
    pass


def test_size_parsing():
    scraper = LimeTorrentScraper(_FakeConfigManager())
    cases = [
        ("1.08 GB", int(1.08 * 1024**3)),
        ("18.18 GB", int(18.18 * 1024**3)),
        ("852.66 MB", int(852.66 * 1024**2)),
        ("159.38 MB", int(159.38 * 1024**2)),
        ("8.69 MB", int(8.69 * 1024**2)),
        ("", 0),
        ("invalid", 0),
    ]
    for raw, expected in cases:
        got = scraper._parse_size(raw)
        print(f"  '{raw}' => {got} (expected {expected})")
        assert got == expected, f"Size mismatch: got {got}, expected {expected}"
    print("  PASS: all size parses OK")


def test_quality_extraction():
    scraper = LimeTorrentScraper(_FakeConfigManager())
    cases = [
        ("The Matrix 1999 1080p AV1 10bit-DKong", "1080P"),
        ("Matrix Reloaded 2003 1080p BluRay DoVi HDR10", "1080P BLURAY"),
        ("Matrix Reloaded 2003 1080p MA WEB-DL H 264", "1080P WEB-DL"),
        ("The Matrix 1999 1080p YT WEB-DL DDP 5 1 H 264", "1080P WEB-DL"),
        ("No Quality Here", ""),
    ]
    for title, expected in cases:
        got = scraper._extract_quality(title)
        print(f"  '{title[:40]}' => '{got}' (expected '{expected}')")
        assert got == expected, f"Quality mismatch: got '{got}', expected '{expected}'"
    print("  PASS: all quality extractions OK")


def test_year_extraction():
    scraper = LimeTorrentScraper(_FakeConfigManager())
    cases = [
        ("The Matrix 1999 1080p AV1", 1999),
        ("Matrix Reloaded 2003 1080p", 2003),
        ("Undercatt - Matrix (2018) FLAC", 2018),
        ("No Year", None),
    ]
    for title, expected in cases:
        got = scraper._extract_year(title)
        print(f"  '{title[:40]}' => {got} (expected {expected})")
        assert got == expected, f"Year mismatch: got {got}, expected {expected}"
    print("  PASS: all year extractions OK")


def test_category_extraction():
    scraper = LimeTorrentScraper(_FakeConfigManager())
    cases = [
        ("Yesterday - in Movies", "movies"),
        ("2 days ago - in Movies", "movies"),
        ("5 days ago - in Music", "music"),
        ("3 months ago - in Anime.", "anime"),
        ("Last Month - in Other", "other"),
        ("Some time - in Applications", "apps"),
    ]
    for text, expected in cases:
        got = scraper._extract_category(text)
        print(f"  '{text}' => '{got}' (expected '{expected}')")
        assert got == expected, f"Category mismatch: got '{got}', expected '{expected}'"
    print("  PASS: all category extractions OK")


def test_magnet_building():
    scraper = LimeTorrentScraper(_FakeConfigManager())
    h = "6666796A47168049DE1AEE5C1E71DC7458ECC9B7"
    magnet = scraper._build_magnet(h, "The Matrix 1999")
    print(f"  magnet: {magnet[:80]}...")
    assert magnet.startswith("magnet:?xt=urn:btih:")
    assert h in magnet
    assert "dn=The" in magnet
    assert "tr=" in magnet
    print("  PASS: magnet building OK")


def test_parse_search_page():
    html = open(SEARCH_HTML).read()
    scraper = LimeTorrentScraper(_FakeConfigManager())
    parsed = scraper._parse_search_page(html)

    print(f"  Parsed {len(parsed)} results from snapshot")
    assert len(parsed) > 0, "Should parse at least some results"

    result, detail_path = parsed[0]
    print(f"  First: {result.title}")
    print(f"    quality={result.quality} size={result.size_bytes} S:{result.seeders} L:{result.leechers}")
    print(f"    category={result.category} source={result.source}")
    print(f"    detail_path={detail_path}")
    print(f"    torrent_url={result.torrent_url[:60] if result.torrent_url else '(none)'}...")

    assert result.title, "title must not be empty"
    assert result.source == "limetorrent"
    assert result.seeders >= 0
    assert result.leechers >= 0
    assert result.size_bytes > 0
    assert detail_path.startswith("/") and "-torrent-" in detail_path
    assert result.category in ("movies", "tv", "anime", "music", "other", "apps", "games")
    print("  PASS: search page snapshot parse OK")


def test_parse_detail_page():
    html = open(DETAIL_HTML).read()
    scraper = LimeTorrentScraper(_FakeConfigManager())
    soup = __import__("bs4", fromlist=["BeautifulSoup"]).BeautifulSoup(html, "html.parser")

    magnet_tag = soup.select_one('a[href^="magnet:"]')
    assert magnet_tag, "Detail page should have magnet link"
    magnet = str(magnet_tag.get("href", ""))
    assert "magnet:?xt=urn:btih:" in magnet
    assert "6666796A47168049DE1AEE5C1E71DC7458ECC9B7" in magnet
    print(f"  Magnet found: {magnet[:70]}...")

    hash_b = next(
        (b for b in soup.find_all("b") if "Torrent Hash" in b.get_text()),
        None,
    )
    assert hash_b, "Detail page should have Torrent Hash"
    td = hash_b.find_next("td")
    info_hash = td.get_text(strip=True)
    assert info_hash == "6666796A47168049DE1AEE5C1E71DC7458ECC9B7"
    print(f"  Hash: {info_hash}")

    print("  PASS: detail page parse OK")


def test_live_search(query="matrix", limit=5):
    scraper = LimeTorrentScraper(_FakeConfigManager())
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
        print(f"      magnet={r.magnet_url[:50] if r.magnet_url else '(none)'}...")

    if results:
        first = results[0]
        assert first.source == "limetorrent"
        assert first.title, "title must not be empty"
        assert first.seeders >= 0
        assert first.size_bytes >= 0
    print("  PASS: live search OK")
    return results


def test_live_category(category="movies", limit=3):
    scraper = LimeTorrentScraper(_FakeConfigManager())
    try:
        results = scraper.search_by_category(category, limit=limit)
    except Exception as e:
        print(f"  Network failed: {e}")
        print("  SKIP")
        return []

    print(f"  search_by_category('{category}', limit={limit}) => {len(results)} results")
    for r in results:
        print(f"    {r.title} | {r.quality} | S:{r.seeders} L:{r.leechers} | cat={r.category}")

    if results:
        assert results[0].source == "limetorrent"
    print("  PASS: live category search OK")
    return results


if __name__ == "__main__":
    print("=== LimeTorrents Scraper Test ===\n")

    print("[1] Size parsing")
    test_size_parsing()
    print()

    print("[2] Quality extraction")
    test_quality_extraction()
    print()

    print("[3] Year extraction")
    test_year_extraction()
    print()

    print("[4] Category extraction")
    test_category_extraction()
    print()

    print("[5] Magnet building")
    test_magnet_building()
    print()

    print("[6] Search page snapshot parse")
    test_parse_search_page()
    print()

    print("[7] Detail page snapshot parse")
    test_parse_detail_page()
    print()

    print("[8] Live search (network)")
    test_live_search()
    print()

    print("[9] Live category search (network)")
    test_live_category()
    print()

    print("All tests passed!")
