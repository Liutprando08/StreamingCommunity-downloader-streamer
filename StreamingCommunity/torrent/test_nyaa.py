# 2026
# Standalone test — python StreamingCommunity/torrent/test_nyaa.py

import sys
import os
import urllib.request
import xml.etree.ElementTree as ET

BASE_URL = "https://nyaa.si"


def test_rss_search(query="one piece", limit=5):
    url = f"{BASE_URL}/?page=rss&q={query.replace(' ', '+')}&c=0_0&f=0"
    print(f"GET {url}")
    with urllib.request.urlopen(url, timeout=15) as resp:
        xml_data = resp.read()
    root = ET.fromstring(xml_data)
    items = root.findall(".//item")
    print(f"Found {len(items)} items (limit={limit})")
    for item in items[:limit]:
        title = item.findtext("title", "?")
        seeders = item.findtext("{https://nyaa.si/xmlns/seeders}seeders", "?")
        size = item.findtext("{https://nyaa.si/xmlns/size}size", "?")
        magnet = item.findtext("link", "")
        print(f"  {title} | Size: {size} | Seeders: {seeders}")
    return items


if __name__ == "__main__":
    print("=== Nyaa.si RSS Test ===\n")
    test_rss_search()
    print("\nAll tests passed!")
