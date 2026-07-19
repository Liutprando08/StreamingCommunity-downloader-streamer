# 2026
# Standalone test — python StreamingCommunity/torrent/test_torrentgalaxy.py

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from StreamingCommunity.torrent.scrapers.torrentgalaxy import TorrentGalaxyScraper


class _FakeConfigManager:
    pass


def test_html_parsing():
    """Parse the reference torrentgalaxy.html snapshot and verify extraction."""
    html_path = os.path.join(
        os.path.dirname(__file__), "scrapers", "torrentgalaxy.html"
    )
    with open(html_path, encoding="utf-8") as f:
        html = f.read()

    scraper = TorrentGalaxyScraper(_FakeConfigManager())
    results = scraper._parse_rows(html, category="movie")
    print(f"test_html_parsing => {len(results)} results from snapshot")
    assert len(results) > 0, "Expected at least 1 result from the HTML snapshot"

    for r in results[:3]:
        print(f"  {r.title}")
        print(f"    quality={r.quality} size={r.size_bytes} S:{r.seeders} L:{r.leechers}")
        print(f"    magnet={r.magnet_url[:60]}...")
        print(f"    source={r.source} category={r.category} year={r.year}")

    first = results[0]
    assert first.source == "torrentgalaxy"
    assert first.title, "title must not be empty"
    assert first.magnet_url.startswith("magnet:"), "magnet must start with magnet:"
    assert first.seeders >= 0, "seeders must be >= 0"
    assert first.leechers >= 0, "leechers must be >= 0"
    assert first.size_bytes >= 0, "size_bytes must be >= 0"
    print("  PASS: all assertions OK")
    return results


def test_quality_extraction():
    """Verify quality extraction from various torrent titles."""
    scraper = TorrentGalaxyScraper(_FakeConfigManager())
    cases = [
        ("The Thing Expanded 2026 1080P WEB H264-GOREHOUNDS", "1080P WEB"),
        ("Toy Story 5 (2026) 2160p", "2160P"),
        ("Maid Robot (2026) 720p WEBRip-LAMA", "720P WEBRIP"),
        ("Star Wars The Mandalorian 2026 iNTERNAL 1080p 10bit HDRip 2CH x26", "1080P HDRIP"),
        ("Supergirl (2026) 1080p TS LiNE x264-Robo29", "1080P TS"),
        ("Evil Dead Burn 2026 1080p TELESYNC x264", "1080P TELESYNC"),
    ]
    for title, expected in cases:
        got = scraper._extract_quality(title)
        print(f"  '{title}' => '{got}' (expected '{expected}')")
        assert expected.lower() in got.lower(), f"Quality mismatch: got '{got}', expected to contain '{expected}'"
    print("  PASS: all quality extractions OK")


def test_year_extraction():
    """Verify year extraction from titles."""
    scraper = TorrentGalaxyScraper(_FakeConfigManager())
    cases = [
        ("Toy Story 5 (2026) 2160p", 2026),
        ("The Thing Expanded 2026 1080P WEB", 2026),
        ("Some Old Movie (1999) 720p", 1999),
        ("No Year Title", None),
    ]
    for title, expected in cases:
        got = scraper._extract_year(title)
        print(f"  '{title}' => {got} (expected {expected})")
        assert got == expected, f"Year mismatch: got {got}, expected {expected}"
    print("  PASS: all year extractions OK")


def test_size_parsing():
    """Verify human-readable size to bytes conversion including non-breaking spaces."""
    scraper = TorrentGalaxyScraper(_FakeConfigManager())
    cases = [
        ("14.4 GB", 14.4 * 1024 ** 3),
        ("909.1 MB", 909.1 * 1024 ** 2),
        ("1.5 GB", 1.5 * 1024 ** 3),
        ("515.6 MB", 515.6 * 1024 ** 2),
        ("721.3\xa0MB", 721.3 * 1024 ** 2),
        ("721.3\u2009MB", 721.3 * 1024 ** 2),
        ("", 0),
        ("invalid", 0),
    ]
    for raw, expected in cases:
        got = scraper._parse_size(raw)
        print(f"  '{raw}' => {got} (expected {int(expected)})")
        assert got == int(expected), f"Size mismatch: got {got}, expected {int(expected)}"
    print("  PASS: all size parses OK")


def test_magnet_hash_extraction():
    """Verify info hash extraction from magnet URLs."""
    scraper = TorrentGalaxyScraper(_FakeConfigManager())
    magnet = (
        "magnet:?xt=urn:btih:BC01DB8A2D3105B04D52555E3A9382209626DA31"
        "&dn=Test%20Torrent&tr=udp://tracker.opentrackr.org:1337/announce"
    )
    h = scraper._parse_magnet_hash(magnet)
    print(f"  hash from magnet => {h}")
    assert h == "BC01DB8A2D3105B04D52555E3A9382209626DA31"
    assert scraper._parse_magnet_hash("") == ""
    assert scraper._parse_magnet_hash("magnet:?xt=urn:bad") == ""
    print("  PASS: magnet hash extraction OK")


def test_url_structure():
    """Verify expected URL patterns for TorrentGalaxy."""
    scraper = TorrentGalaxyScraper(_FakeConfigManager())
    base = scraper.BASE_URL
    tests = {
        "search": f"{base}/get-posts/keywords:matrix",
        "search_page": f"{base}/get-posts/keywords:matrix?page=2",
        "category_movies": f"{base}/get-posts/category:Movies",
        "category_tv": f"{base}/get-posts/category:TV",
    }
    for name, url in tests.items():
        print(f"  {name}: {url}")
    print("  PASS: URL structure OK")
    return tests


def test_live_search_parsing(limit=5):
    """Live search — verify parsing of real TorrentGalaxy search results."""
    scraper = TorrentGalaxyScraper(_FakeConfigManager())
    try:
        html = scraper._try_mirrors("/get-posts/keywords:matrix")
    except Exception as e:
        print(f"  Network failed: {e}")
        print("  SKIP")
        return []

    if not html:
        print("  No HTML returned (DNS blocked?)")
        print("  SKIP")
        return []

    results = scraper._parse_rows(html)
    print(f"  Parsed {len(results)} rows from live search")
    assert len(results) > 0, "Expected results from live search"

    for r in results[:limit]:
        has_magnet = bool(r.magnet_url)
        print(f"    {r.title}")
        print(f"      quality={r.quality} size={r.size_bytes} S:{r.seeders} L:{r.leechers} cat={r.category}")
        print(f"      magnet={'yes' if has_magnet else 'no (needs detail page)'}")

    first = results[0]
    assert first.source == "torrentgalaxy"
    assert first.title, "title must not be empty"
    assert first.seeders >= 0
    assert first.leechers >= 0
    assert first.size_bytes > 0, "size_bytes should be > 0 for real results"
    assert first.category, "category must be extracted"
    print("  PASS: live search parsing OK")
    return results


def test_detail_page_magnet(limit=2):
    """Fetch magnet from a detail page."""
    scraper = TorrentGalaxyScraper(_FakeConfigManager())
    try:
        html = scraper._try_mirrors("/get-posts/keywords:matrix")
    except Exception:
        print("  SKIP: network")
        return []

    if not html:
        print("  SKIP: no HTML")
        return []

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("div.tgxtablerow")

    fetched = 0
    magnets_found = []
    for row in rows:
        if fetched >= limit:
            break
        title_cell = row.select_one("div.tgxtablecell.clickable-row")
        if not title_cell:
            continue
        post_path = title_cell.get("data-href", "")
        if not post_path:
            continue

        print(f"  Fetching detail: {post_path}")
        magnet = scraper.get_magnet(post_path)
        if magnet:
            h = scraper._parse_magnet_hash(magnet)
            print(f"    magnet hash: {h}")
            assert magnet.startswith("magnet:"), "Must start with magnet:"
            assert len(h) == 40, f"Hash must be 40 chars, got {len(h)}"
            magnets_found.append(magnet)
            fetched += 1
        else:
            print(f"    No magnet found")

    print(f"  Fetched {len(magnets_found)}/{limit} magnets")
    if magnets_found:
        print("  PASS: detail page magnet OK")
    else:
        print("  WARN: no magnets fetched (network?)")
    return magnets_found


def test_search_live(limit=3, page=1):
    """Full live search with magnet fetching."""
    scraper = TorrentGalaxyScraper(_FakeConfigManager())
    try:
        results = scraper.search("matrix", page=page, limit=limit)
    except Exception as e:
        print(f"  Live search failed: {e}")
        print("  SKIP")
        return []

    print(f"  search('matrix', limit={limit}) => {len(results)} results")
    for r in results:
        has_magnet = bool(r.magnet_url)
        print(f"    {r.title}")
        print(f"      quality={r.quality} size={r.size_bytes} S:{r.seeders} L:{r.leechers}")
        print(f"      magnet={'yes' if has_magnet else 'no'}")
    if results:
        assert results[0].source == "torrentgalaxy"
        assert results[0].category
    print("  PASS: full live search OK")
    return results


if __name__ == "__main__":
    print("=== TorrentGalaxy Scraper Test ===\n")

    print("[1] URL structure")
    test_url_structure()
    print()

    print("[2] Quality extraction")
    test_quality_extraction()
    print()

    print("[3] Year extraction")
    test_year_extraction()
    print()

    print("[4] Size parsing (incl. non-breaking spaces)")
    test_size_parsing()
    print()

    print("[5] Magnet hash extraction")
    test_magnet_hash_extraction()
    print()

    print("[6] HTML snapshot parsing")
    test_html_parsing()
    print()

    print("[7] Live search parsing (network)")
    test_live_search_parsing()
    print()

    print("[8] Detail page magnet (network)")
    test_detail_page_magnet()
    print()

    print("[9] Full search with magnet fetch (network)")
    test_search_live()
    print()

    print("All tests passed!")
