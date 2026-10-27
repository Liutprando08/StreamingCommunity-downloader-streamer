# Site health checker.
#
# The application talks to many scraper targets whose domains change often.
# This module answers one question for the user: "is this site reachable right
# now?" — it does not validate scraping logic, only DNS/TLS/HTTP reachability.
#
# Domains come from ``Conf/domains.json`` when configured; services that
# hardcode their host still get a sensible homepage fallback so the report
# covers every entry in the site registry.

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from rich.markup import escape
from rich.table import Table

from StreamingCommunity.services._base.site_loader import SITE_REGISTRY
from StreamingCommunity.utils import config_manager
from StreamingCommunity.utils.http_client import create_client

logger = logging.getLogger(__name__)

WORKING = "working"
UNREACHABLE = "unreachable"
UNKNOWN = "unknown"

# Homepages for services that hardcode their host instead of reading
# ``domains.json``. Keep this in sync with the site registry; a missing entry
# is reported as "unknown" rather than failing the whole check.
FALLBACK_URLS: dict[str, str] = {
    "raiplay": "https://www.raiplay.it",
    "mediasetinfinity": "https://mediasetinfinity.mediaset.it",
    "tubitv": "https://tubitv.com",
    "ipersphera": "https://www.ipersphera.com",
    "discoveryus": "https://www.discovery.com",
    "discoveryeu": "https://www.discoveryplus.com",
    "realtime": "https://realtime.it",
    "dmax": "https://www.dmax.it",
    "nove": "https://www.nove.tv",
    "homegardentv": "https://www.homegardentv.it",
}

# A health check should fail fast: waiting for the normal request timeout on
# every dead domain would make the command take minutes.
DEFAULT_TIMEOUT = 8.0
DEFAULT_WORKERS = 8

_STATUS_TEXT = {
    WORKING: ("Working", "Funzionante"),
    UNREACHABLE: ("Unreachable", "Non raggiungibile"),
    UNKNOWN: ("Unknown", "Sconosciuto"),
}
_STATUS_COLOR = {
    WORKING: "#a6e3a1",
    UNREACHABLE: "#f38ba8",
    UNKNOWN: "#f9e2af",
}


@dataclass(frozen=True)
class SiteStatus:
    """Result of one site reachability probe."""

    name: str
    url: str
    status: str
    http_status: int | None = None
    latency_ms: int | None = None
    detail: str = ""


def status_text(status: str, *, italian: bool = False) -> str:
    """Return the human label for a status (English CLI / Italian TUI)."""
    texts = _STATUS_TEXT.get(status, _STATUS_TEXT[UNKNOWN])
    return texts[1] if italian else texts[0]


def status_color(status: str) -> str:
    return _STATUS_COLOR.get(status, _STATUS_COLOR[UNKNOWN])


def configured_url(site_name: str) -> str:
    """Return the URL to probe for ``site_name`` (empty when unknown)."""
    try:
        configured = config_manager.domain.get(site_name, "full_url", default="")
    except (AttributeError, TypeError, ValueError):
        configured = ""
    url = str(configured or "").strip()
    return url or FALLBACK_URLS.get(site_name, "")


def discover_sites() -> list[tuple[str, str]]:
    """Return ``(site_name, url)`` pairs in registry order.

    Only services present in the registry are checked; a registry entry with
    no known URL is kept with an empty URL so the report can show "unknown"
    instead of silently hiding it.
    """
    sites = [(name, configured_url(name)) for name in SITE_REGISTRY]
    known = set(SITE_REGISTRY)
    try:
        domains = config_manager.domain._config_dict
    except AttributeError:
        return sites
    for name in domains:
        if name not in known:
            sites.append((name, configured_url(name)))
    return sites


def check_site(
    name: str,
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> SiteStatus:
    """Probe one site and classify the outcome.

    Any HTTP response below 500 counts as reachable: a 403/429 usually means
    the server is up but blocks bots, which still tells the user the domain is
    alive. Connection failures and 5xx responses are "unreachable".
    """
    if not url:
        return SiteStatus(
            name=name,
            url="",
            status=UNKNOWN,
            detail="no domain configured",
        )

    started = time.monotonic()
    try:
        with create_client(timeout=timeout) as client:
            response = client.get(url)
    except Exception as exc:  # noqa: BLE001 - one broken site must not abort the report
        elapsed = int((time.monotonic() - started) * 1000)
        logger.info("Site check failed for %s (%s): %s", name, url, exc)
        return SiteStatus(
            name=name,
            url=url,
            status=UNREACHABLE,
            latency_ms=elapsed,
            detail=str(exc).strip()[:120],
        )

    elapsed = int((time.monotonic() - started) * 1000)
    status = WORKING if response.status_code < 500 else UNREACHABLE
    detail = ""
    final_url = str(response.url).rstrip("/")
    if final_url and final_url != url.rstrip("/"):
        detail = f"redirected to {final_url}"
    if not detail and response.status_code >= 400:
        detail = "server responded, but may block bots"

    logger.info(
        "Site check: %s -> %s (HTTP %s, %d ms)",
        name,
        status,
        response.status_code,
        elapsed,
    )
    return SiteStatus(
        name=name,
        url=url,
        status=status,
        http_status=response.status_code,
        latency_ms=elapsed,
        detail=detail,
    )


def iter_site_checks(
    sites: Iterable[tuple[str, str]] | None = None,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_workers: int = DEFAULT_WORKERS,
) -> Iterator[SiteStatus]:
    """Yield probe results as each site finishes (used by the TUI)."""
    site_list = list(discover_sites() if sites is None else sites)
    if not site_list:
        return

    workers = max(1, min(max_workers, len(site_list)))
    pool = ThreadPoolExecutor(max_workers=workers)
    futures = [
        pool.submit(check_site, name, url, timeout=timeout) for name, url in site_list
    ]
    try:
        for future in as_completed(futures):
            yield future.result()
    finally:
        # Never block the caller on a hung socket after the results are in.
        pool.shutdown(wait=False)


def check_sites(
    sites: Iterable[tuple[str, str]] | None = None,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_workers: int = DEFAULT_WORKERS,
) -> list[SiteStatus]:
    """Check every site and return results in registry order."""
    site_list = list(discover_sites() if sites is None else sites)
    order = {name: index for index, (name, _) in enumerate(site_list)}
    results = list(
        iter_site_checks(site_list, timeout=timeout, max_workers=max_workers)
    )
    return sorted(results, key=lambda result: order.get(result.name, len(order)))


def summary_counts(results: Iterable[SiteStatus]) -> dict[str, int]:
    """Count results per status (always includes the three known keys)."""
    counts = {WORKING: 0, UNREACHABLE: 0, UNKNOWN: 0}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    return counts


def render_table(results: Iterable[SiteStatus]) -> Table:
    """Build the Rich table used by ``--check-sites``."""
    table = Table(title="Site health", title_justify="left")
    table.add_column("Site", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("HTTP", justify="right", no_wrap=True)
    table.add_column("Latency", justify="right", no_wrap=True)
    table.add_column("URL / note", overflow="fold")

    for result in results:
        label = status_text(result.status)
        color = status_color(result.status)
        http = str(result.http_status) if result.http_status is not None else "-"
        latency = f"{result.latency_ms} ms" if result.latency_ms is not None else "-"
        target = escape(result.url) if result.url else "-"
        if result.detail:
            target = f"{target}\n[dim]{escape(result.detail)}[/]"
        table.add_row(
            result.name,
            f"[{color}]{label}[/]",
            http,
            latency,
            target,
        )
    return table
