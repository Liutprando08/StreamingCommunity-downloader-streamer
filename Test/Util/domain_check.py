# Simple manual test for the StreamingCommunity domain check on startup

import json
import sys

from StreamingCommunity.utils import config_manager
from StreamingCommunity.utils.domain_check import (
    SCRAPER_URL,
    check_streamingcommunity_domain,
    _extract_domain,
    fetch_scraped_domain,
    is_same_domain,
)

SITE_NAME = "streamingcommunity"
CACHE_KEY = f"domain.{SITE_NAME}.full_url"


def _set_flag(value):
    config_manager.config.set_key("DEFAULT", "check_domain_on_start", value)


def _set_domain(url):
    config_manager.domain.set_key(SITE_NAME, "full_url", url)


def _current_domain():
    return config_manager.domain.get(SITE_NAME, "full_url", default="")


def main():
    # Snapshot current state so it can be restored afterwards (raw file + memory)
    with open(config_manager.domains_path, "rb") as fp:
        original_bytes = fp.read()
    original_data = json.loads(json.dumps(config_manager._domains_data))

    try:
        # 1) Pure link-extraction logic
        sample = (
            '<p><span style="color: #ff0000;"><strong>'
            "https://streaming-community.ltd/</strong></span>"
        )
        assert _extract_domain(sample) == "https://streaming-community.ltd"
        assert _extract_domain("no link here") is None
        assert is_same_domain("https://a.com/", "https://a.com/x")
        assert not is_same_domain(
            "https://streaming-community.ltd/", "https://streaming-community.futbol/"
        )
        print("OK: link-extraction logic")

        # 2) Disabled flag -> no network request, returns False
        _set_flag(False)
        assert check_streamingcommunity_domain() is False
        _set_flag(True)
        print("OK: check skipped when flag is disabled")

        # 3) End-to-end: scrape the link page and find a StreamingCommunity URL
        scraped = fetch_scraped_domain()
        if scraped is None:
            print("SKIP: link page unavailable, no domain scraped")
        else:
            assert scraped.startswith("https://streaming-community."), scraped
            print(f"OK: scraped current domain {scraped} from {SCRAPER_URL}")

            # 4) A stale configured domain is replaced by the scraped one
            _set_domain("https://streaming-community.example/")
            updated = check_streamingcommunity_domain()
            assert updated is True, "expected the stale domain to be replaced"
            assert _current_domain() == scraped
            print(f"OK: stale domain replaced with {scraped}")

            # 5) Up-to-date domain -> returns False, no change
            assert check_streamingcommunity_domain() is False
            print("OK: unchanged domain left untouched")

    finally:
        # Restore the original domains configuration (file + memory) and re-enable the flag
        with open(config_manager.domains_path, "wb") as fp:
            fp.write(original_bytes)
        config_manager._domains_data.clear()
        config_manager._domains_data.update(original_data)
        config_manager.cache.pop(CACHE_KEY, None)
        _set_flag(True)

    print("ALL TESTS PASSED")


if __name__ == "__main__":
    sys.exit(main())
