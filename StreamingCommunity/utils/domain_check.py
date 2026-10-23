# 11.08.26 - Auto-detect StreamingCommunity / AnimeWorld domain changes

import logging
import re
from urllib.parse import urlparse

from httpx2 import HTTPError

# Internal utilities
from StreamingCommunity.utils import config_manager
from StreamingCommunity.utils.console.shared import console
from StreamingCommunity.utils.http_client import create_client


# Variable
SITE_NAME = "streamingcommunity"
SCRAPER_URL = "https://www.giardiniblog.it/streamingcommunity-nuovo-link/"
ANIMEWORLD_SITE_NAME = "animeworld"
ANIMEWORLD_SCRAPER_URL = "https://www.giardiniblog.it/animeworld-nuovo/"
ANIMEUNITY_SITE_NAME = "animeunity"
ANIMEUNITY_SCRAPER_URL = "https://natchecker.com/it/blog/animeunity"
DEFAULT_TIMEOUT = 10.0
URL_PATTERN = re.compile(r"https?://streaming-community\.[a-z0-9.-]+/?")
ANIMEWORLD_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?animeworld\.[a-z0-9.-]+/?"
)
ANIMEUNITY_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?animeunity\.[a-z0-9.-]+/?"
)
logger = logging.getLogger(__name__)


def _host(url: str) -> str:
    """Return the normalized host (netloc, lowercased) of a URL."""
    return urlparse(url).netloc.lower()


def resolve_final_url(current_url: str, timeout: float = DEFAULT_TIMEOUT) -> str:
    """Follow redirects from current_url and return the final effective URL."""
    with create_client(timeout=timeout) as client:
        response = client.get(current_url)
    try:
        if response is None:
            raise ValueError()
    except ValueError as e:
        logger.error(f"response:{e}")
    return str(response.url)


def is_same_domain(current_url: str, final_url: str) -> bool:
    """True if the host of the final URL matches the configured one."""
    return _host(current_url) == _host(final_url)


def _extract_domain(
    html: str, pattern: re.Pattern[str] = URL_PATTERN
) -> str | None:
    """Extract the site URL advertised on a link-check page."""
    match = pattern.search(html or "")
    return match.group(0).rstrip("/") if match else None


def fetch_scraped_domain(
    timeout: float = DEFAULT_TIMEOUT,
    scraper_url: str = SCRAPER_URL,
    pattern: re.Pattern[str] = URL_PATTERN,
) -> str | None:
    """Scrape a link page and return the current domain advertised there."""
    with create_client(timeout=timeout) as client:
        response = client.get(scraper_url)
    try:
        if response is None:
            raise ValueError()
    except ValueError as e:
        logger.error(f"response:{e}")
    return _extract_domain(response.text, pattern)


def _update_domain(
    current_url: str, new_url: str, site_name: str = SITE_NAME
) -> None:
    """Update a service domain in memory and on disk."""
    config_manager.domain.set_key(site_name, "full_url", new_url)
    config_manager.save_domains()
    console.print(
        f"[green]Domain updated: [yellow]{current_url or 'unknown'}[/yellow] → [cyan]{new_url}"
    )


def _check_domain(
    site_name: str,
    scraper_url: str,
    pattern: re.Pattern[str],
    timeout: float = DEFAULT_TIMEOUT,
) -> bool:
    """Run the shared link-check flow for one service.

    Scrapes ``scraper_url`` to find the current domain, then falls back to
    redirect detection on the configured domain when the page is unavailable.
    Returns True when the domain was updated. Never blocks a search: any
    failure is logged and skipped.
    """
    try:
        enabled = config_manager.config.get_bool(
            "DEFAULT", "check_domain_on_start", default=True
        )
        if not enabled:
            return False

        current_url = config_manager.domain.get(site_name, "full_url", default="")
        try:
            scraped_url = fetch_scraped_domain(timeout, scraper_url, pattern)
        except Exception as exc:
            # The link tracker can be temporarily unreachable; still try the
            # redirect fallback below instead of giving up immediately.
            logger.warning(f"Link page request failed for {site_name}: {exc}")
            scraped_url = None

        if scraped_url:
            if current_url and is_same_domain(current_url, scraped_url):
                console.print(
                    f"[cyan]Domain check: [green]{site_name}[/green] → [yellow]{scraped_url}"
                )
                return False

            _update_domain(current_url, scraped_url, site_name)
            return True

        # Fallback: follow redirects on the configured domain
        if not current_url:
            return False

        final_url = resolve_final_url(current_url, timeout)
        if is_same_domain(current_url, final_url):
            console.print(
                f"[cyan]Domain check: [green]{site_name}[/green] → [yellow]{current_url}"
            )
            return False

        _update_domain(current_url, final_url.rstrip("/"), site_name)
        return True

    except HTTPError as e:
        logger.warning(f"Domain check skipped for {site_name}: {e}")
        return False
    except Exception as e:  # a broken link checker must never block a search
        logger.warning(f"Domain check failed for {site_name}: {e}")
        return False


def check_streamingcommunity_domain() -> bool:
    """Check the current StreamingCommunity domain and update domains.json if it changed.

    Scrapes the link page (giardiniblog.it) to find the current domain.
    Falls back to redirect detection on the configured domain when the page is
    unavailable. Runs once, before the first StreamingCommunity search.
    """
    return _check_domain(SITE_NAME, SCRAPER_URL, URL_PATTERN)


def check_animeworld_domain() -> bool:
    """Check the current AnimeWorld domain and update domains.json if it changed.

    Uses the GiardiniBlog AnimeWorld link page, with redirect detection as a
    fallback. Called once before the first AnimeWorld search.
    """
    return _check_domain(
        ANIMEWORLD_SITE_NAME, ANIMEWORLD_SCRAPER_URL, ANIMEWORLD_URL_PATTERN
    )


def check_animeunity_domain() -> bool:
    """Check the current AnimeUnity domain and update domains.json if it changed.

    Uses natchecker.com as source, with redirect detection as a fallback.
    Called once before the first AnimeUnity search.
    """
    return _check_domain(
        ANIMEUNITY_SITE_NAME, ANIMEUNITY_SCRAPER_URL, ANIMEUNITY_URL_PATTERN
    )
