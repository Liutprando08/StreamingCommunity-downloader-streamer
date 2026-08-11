# 11.08.26 - Auto-detect StreamingCommunity domain changes on startup

import logging
import re
from urllib.parse import urlparse

from httpx import HTTPError
from rich.console import Console

# Internal utilities
from StreamingCommunity.utils import config_manager
from StreamingCommunity.utils.http_client import create_client


# Variable
console = Console()
SITE_NAME = "streamingcommunity"
SCRAPER_URL = "https://www.giardiniblog.it/streamingcommunity-nuovo-link/"
DEFAULT_TIMEOUT = 10.0
URL_PATTERN = re.compile(r"https?://streaming-community\.[a-z0-9.-]+/?")
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


def _extract_domain(html: str) -> str | None:
    """Extract the StreamingCommunity URL advertised on the scraper page."""
    match = URL_PATTERN.search(html or "")
    return match.group(0).rstrip("/") if match else None


def fetch_scraped_domain(timeout: float = DEFAULT_TIMEOUT) -> str | None:
    """Scrape the link page and return the current StreamingCommunity URL."""
    with create_client(timeout=timeout) as client:
        response = client.get(SCRAPER_URL)
    try:
        if response is None:
            raise ValueError()
    except ValueError as e:
        logger.error(f"response:{e}")
    return _extract_domain(response.text)


def _update_domain(current_url: str, new_url: str) -> None:
    """Update the streamingcommunity domain in memory and on disk."""
    config_manager.domain.set_key(SITE_NAME, "full_url", new_url)
    config_manager.save_domains()
    console.print(
        f"[green]Domain updated: [yellow]{current_url or 'unknown'}[/yellow] → [cyan]{new_url}"
    )


def check_streamingcommunity_domain() -> bool:
    """Check the current StreamingCommunity domain and update domains.json if it changed.

    Scrapes the link page (giardiniblog.it) to find the current domain.
    Falls back to redirect detection on the configured domain when the page is
    unavailable. Runs on every app opening. Returns True when the domain was
    updated. Never blocks startup: any failure is logged and skipped.
    """
    try:
        enabled = config_manager.config.get_bool(
            "DEFAULT", "check_domain_on_start", default=True
        )
        if not enabled:
            return False

        current_url = config_manager.domain.get(SITE_NAME, "full_url", default="")
        scraped_url = fetch_scraped_domain()

        if scraped_url:
            if current_url and is_same_domain(current_url, scraped_url):
                console.print(
                    f"[cyan]Domain check: [green]{SITE_NAME}[/green] → [yellow]{scraped_url}"
                )
                return False

            _update_domain(current_url, scraped_url)
            return True

        # Fallback: follow redirects on the configured domain
        if not current_url:
            return False

        final_url = resolve_final_url(current_url)
        if is_same_domain(current_url, final_url):
            console.print(
                f"[cyan]Domain check: [green]{SITE_NAME}[/green] → [yellow]{current_url}"
            )
            return False

        _update_domain(current_url, final_url.rstrip("/"))
        return True

    except HTTPError as e:
        logger.warning(f"Domain check skipped for {SITE_NAME}: {e}")
        return False
