# 2026
# Standalone test — python StreamingCommunity/torrent/test_eztv.py

import json
import sys
import os
import urllib.request

BASE_URL = "https://eztvx.to/api"


def test_get_torrents(limit=3, page=1):
    url = f"{BASE_URL}/get-torrents?limit={limit}&page={page}"
    print(f"GET {url}")
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.loads(resp.read())
    print(f"torrents_count: {data.get('torrents_count', '?')}")
    for t in data.get("torrents", []):
        print(f"  [{t['id']}] {t['title']} | {t['size_bytes']} bytes | S:{t['seeds']} L:{t['peers']}")
    return data


def test_imdb_lookup(imdb_id="6048596", limit=3):
    url = f"{BASE_URL}/get-torrents?imdb_id={imdb_id}&limit={limit}"
    print(f"GET {url}")
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.loads(resp.read())
    print(f"torrents_count: {data.get('torrents_count', '?')} for imdb_id={imdb_id}")
    for t in data.get("torrents", []):
        print(f"  [{t['id']}] S{t['season']}E{t['episode']} {t['title']} | {t['size_bytes']} bytes")
    return data


if __name__ == "__main__":
    print("=== EZTV API Test ===\n")
    test_get_torrents()
    print()
    test_imdb_lookup()
    print("\nAll tests passed!")
