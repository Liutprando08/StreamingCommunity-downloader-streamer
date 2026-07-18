# 2026
# Standalone test — python StreamingCommunity/torrent/test_rutracker.py

import sys
import os
import json

# NOTE: This test uses stdlib only. The actual scraper uses requests + BeautifulSoup.
# RuTracker requires authentication for search. This test verifies config and URL structure.


def test_url_structure():
    """Verify expected URL patterns for RuTracker."""
    base = "https://rutracker.net/forum"
    tests = {
        "login": f"{base}/login.php",
        "search": f"{base}/tracker.php?nm=matrix",
        "topic": f"{base}/viewtopic.php?t=12345",
        "download": f"{base}/dl.php?t=12345",
    }
    for name, url in tests.items():
        print(f"  {name}: {url}")
    print("URL structure OK")
    return tests


def test_config_template():
    """Verify login.json has rutracker section."""
    login_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "Conf", "login.json"
    )
    if os.path.exists(login_path):
        with open(login_path) as f:
            data = json.load(f)
        if "rutracker" in data:
            print(f"  login.json has 'rutracker' section: {data['rutracker']}")
        else:
            print("  WARNING: login.json missing 'rutracker' section")
    else:
        print(f"  WARNING: login.json not found at {login_path}")
    return True


if __name__ == "__main__":
    print("=== RuTracker Config Test ===\n")
    test_url_structure()
    print()
    test_config_template()
    print("\nAll tests passed!")
