# Cross-provider ("global") search used by the TUI home screen.
#
# The home search box fans a query out over every provider of the selected
# sector and streams results back as they arrive. Providers declare their
# sector either explicitly (``sector = "music"``) or implicitly through their
# ``category``; ``sector_of`` keeps that mapping in one place so the home tabs
# stay data-driven.

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any

from .providers import registry

logger = logging.getLogger(__name__)

# (key, label) in tab order. The key is what ``Tab.id`` carries.
SECTORS: tuple[tuple[str, str], ...] = (
    ("all", "Tutti"),
    ("film", "Film"),
    ("music", "Music"),
    ("other", "Altro"),
)

# Categories that belong to the "Film" tab (film, serie and anime catalogs).
_FILM_CATEGORIES = {"Film", "Film_Serie", "Serie", "Anime"}

# How many providers to query at once. Bound so a global search does not open a
# socket to every site in the registry at the same time.
_MAX_WORKERS = 8


def sector_of(provider: Any) -> str:
    """Return the sector key a provider belongs to.

    An explicit ``sector`` attribute wins; otherwise the provider's
    ``category`` (or the music flow) decides.
    """
    explicit = getattr(provider, "sector", None)
    if explicit:
        return str(explicit)
    category = str(getattr(provider, "category", "") or "")
    if category == "Music" or getattr(provider, "flow", "") == "music":
        return "music"
    if category in _FILM_CATEGORIES:
        return "film"
    return "other"


def providers_for_sector(sector: str) -> list:
    """Return the registered providers belonging to ``sector``.

    ``""``/``"all"``/``None`` means every provider.
    """
    providers = registry.all()
    if sector in ("", "all", None):
        return providers
    return [p for p in providers if sector_of(p) == sector]


def search_provider(provider: Any, query: str) -> list:
    """Run one provider's search, adapting the call to its flow.

    Music providers need a mode; the global search always uses their first
    (usually "Song") so a single query bar works for every sector.
    """
    if getattr(provider, "flow", "") == "music":
        modes = provider.search_modes()
        if not modes:
            return []
        return list(provider.search(query, modes[0]))
    return list(provider.search(query))


def _job(provider: Any, query: str) -> tuple[Any, list, BaseException | None]:
    try:
        return provider, search_provider(provider, query), None
    except Exception as exc:  # one broken site must not abort the whole search
        return provider, [], exc


def aggregate_search(
    providers: Iterable[Any], query: str, timeout: float | None = 60.0
) -> Iterator[tuple[Any, list, BaseException | None]]:
    """Search every provider in parallel, yielding ``(provider, entries, error)``.

    Results are yielded as each provider finishes (not in registry order) so the
    caller can populate its table live. ``error`` is the exception raised by a
    provider, or ``None`` on success.

    ``timeout`` caps the total wait: once it elapses the generator stops even if
    a provider is still running, so a single hung site cannot freeze the caller
    forever. Abandoned requests keep running in the background.
    """
    providers = list(providers)
    if not providers:
        return

    workers = min(_MAX_WORKERS, len(providers))
    pool = ThreadPoolExecutor(max_workers=workers)
    futures = [pool.submit(_job, provider, query) for provider in providers]
    try:
        for future in as_completed(futures, timeout=timeout):
            yield future.result()
    except FuturesTimeoutError:
        logger.warning("Global search timed out after %ss", timeout)
    finally:
        # Do not join: a stuck request must not block the UI worker thread.
        pool.shutdown(wait=False)
