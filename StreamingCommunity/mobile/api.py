"""Minimal headless API used by the Android shell.

Only services that already use the yt-dlp download engine are exposed.  The
module is intentionally synchronous; the Kivy app calls it from worker threads
and polls :func:`download_state` from the UI thread.
"""

from __future__ import annotations

import importlib
import threading
import uuid
from typing import Any, Callable

# Imported after ``bootstrap.prepare()`` in the Android app.
from StreamingCommunity.services._base.object import Entries
from StreamingCommunity.source.utils.tracker import context_tracker, download_tracker

SERVICES: dict[str, dict[str, str]] = {
    "streamingcommunity": {
        "label": "StreamingCommunity",
        "module": "StreamingCommunity.services.streamingcommunity",
    },
    "altadefinizione": {
        "label": "Altadefinizione",
        "module": "StreamingCommunity.services.altadefinizione",
    },
}

_LOCK = threading.RLock()
_modules: dict[str, Any] = {}
_scrapper_modules: dict[str, Any] = {}
_scrapers: dict[tuple[str, str], Any] = {}


class MobileError(RuntimeError):
    """Raised for user-facing failures in the mobile API."""


def configure() -> None:
    """Switch the shared engine into headless (UI) mode.

    This disables Rich progress rendering and console-only output while keeping
    :class:`~StreamingCommunity.source.utils.tracker.DownloadTracker` updates
    available for the UI.
    """
    context_tracker.is_gui = True


def list_services() -> list[dict[str, str]]:
    return [
        {"id": key, "label": value["label"]}
        for key, value in SERVICES.items()
    ]


def _load(service: str):
    if service not in SERVICES:
        raise MobileError(f"Unsupported service: {service}")

    with _LOCK:
        module = _modules.get(service)
        if module is None:
            module = importlib.import_module(SERVICES[service]["module"])
            _modules[service] = module
        return module


def _entry_payload(entry: Entries) -> dict[str, Any]:
    return {
        "id": entry.id,
        "name": entry.name or "",
        "type": entry.type or "film",
        "year": entry.year or "",
        "url": entry.url or "",
        "imdb_id": getattr(entry, "imdb_id", "") or "",
        "slug": entry.slug or "",
        "desc": entry.desc or "",
        "score": entry.score or "",
    }


def _entry_from_payload(payload: dict[str, Any]) -> Entries:
    return Entries(
        id=payload.get("id"),
        name=payload.get("name"),
        type=payload.get("type") or "film",
        url=payload.get("url"),
        year=payload.get("year") or "",
        imdb_id=payload.get("imdb_id") or "",
        slug=payload.get("slug") or "",
        desc=payload.get("desc") or "",
        score=payload.get("score") or "",
    )


def search(service: str, query: str, limit: int = 30) -> list[dict[str, Any]]:
    """Search a service and return JSON-friendly entries."""
    query = (query or "").strip()
    if not query:
        return []

    module = _load(service)
    try:
        with _LOCK:
            module.title_search(query)
            entries = list(module.entries_manager.media_list)[:limit]
    except Exception as exc:  # network / parsing errors become user-facing
        raise MobileError(f"Search failed: {exc}") from exc

    return [_entry_payload(entry) for entry in entries]


def _scraper(service: str, entry: Entries):
    _load(service)
    with _LOCK:
        scrapper_module = _scrapper_modules.get(service)
        if scrapper_module is None:
            scrapper_module = importlib.import_module(
                f"{SERVICES[service]['module']}.scrapper"
            )
            _scrapper_modules[service] = scrapper_module

        key = (service, entry.url or str(entry.imdb_id))
        scraper = _scrapers.get(key)
        if scraper is None:
            scraper = scrapper_module.GetSerieInfo(
                entry.imdb_id,
                entry.name,
                url=entry.url,
            )
            _scrapers[key] = scraper
        return scraper


def get_details(service: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Return seasons/episodes for a series entry, or a film marker."""
    entry = _entry_from_payload(payload)
    if (entry.type or "film") != "tv":
        return {"type": "film", "name": entry.name, "seasons": []}

    try:
        scraper = _scraper(service, entry)
        scraper.getNumberSeason()
        seasons: list[dict[str, Any]] = []
        for season in scraper.seasons_manager.seasons:
            episodes = scraper.getEpisodeSeasons(season.number)
            seasons.append(
                {
                    "number": season.number,
                    "episodes": [
                        {
                            "index": index + 1,
                            "number": getattr(episode, "number", index + 1),
                            "name": episode.name or f"Episodio {index + 1}",
                        }
                        for index, episode in enumerate(episodes)
                    ],
                }
            )
    except Exception as exc:
        raise MobileError(f"Could not load episodes: {exc}") from exc

    return {"type": "series", "name": entry.name, "seasons": seasons}


def _media_type(entry: Entries) -> str:
    return "Serie" if (entry.type or "film") == "tv" else "Film"


def _title(entry: Entries, season: int | None, episode: int | None) -> str:
    if season is None or episode is None:
        return entry.name or "Download"
    return f"{entry.name or 'Series'} S{season}E{episode}"


def download(
    service: str,
    payload: dict[str, Any],
    season: int | None = None,
    episode: int | None = None,
    download_id: str | None = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Download a film or a single episode. Blocking: call from a thread."""
    module = _load(service)
    entry = _entry_from_payload(payload)
    download_id = download_id or uuid.uuid4().hex[:12]

    context_tracker.is_gui = True
    context_tracker.download_id = download_id
    context_tracker.site_name = service
    context_tracker.media_type = _media_type(entry)
    context_tracker.title = _title(entry, season, episode)

    download_tracker.start_download(
        download_id,
        context_tracker.title,
        service,
        context_tracker.media_type,
    )
    download_tracker.update_status(download_id, "starting")

    if on_event:
        on_event({"event": "started", "download_id": download_id})

    result: Any = None
    error: str | None = None
    try:
        if season is not None and episode is not None:
            scraper = _scraper(service, entry)
            episodes = scraper.getEpisodeSeasons(season)
            if not (1 <= episode <= len(episodes)):
                raise MobileError(
                    f"Episode {episode} is out of range (1-{len(episodes)})"
                )
            result = module.download_episode(
                episodes[episode - 1], season, episode, scraper
            )
        else:
            result = module.download_film(entry)
    except Exception as exc:
        error = str(exc)
        download_tracker.update_status(download_id, "failed")

    path: str | None = None
    stopped = False
    if isinstance(result, tuple):
        path = result[0]
        stopped = bool(result[1]) if len(result) > 1 else False
    elif isinstance(result, str):
        path = result

    success = bool(path) and not error and not stopped
    if not success and error is None:
        if stopped:
            error = "cancelled"
        elif result is None:
            error = "No downloadable stream found"

    # yt-dlp already closes the tracker entry; this is a no-op in that case.
    download_tracker.complete_download(
        download_id,
        success=success,
        error=error,
        path=path,
    )

    if on_event:
        on_event(
            {
                "event": "finished",
                "download_id": download_id,
                "success": success,
                "path": path,
                "error": error,
            }
        )

    return {
        "download_id": download_id,
        "success": success,
        "path": path,
        "stopped": stopped,
        "error": error,
    }


def download_state(download_id: str) -> dict[str, Any] | None:
    """Return the latest tracker snapshot for a download (UI polling)."""
    for item in download_tracker.get_active_downloads():
        if item.get("id") == download_id:
            return item
    for item in download_tracker.get_history():
        if item.get("id") == download_id:
            return item
    return None


def cancel(download_id: str) -> None:
    download_tracker.request_stop(download_id)


def history(limit: int = 20) -> list[dict[str, Any]]:
    return download_tracker.get_history()[:limit]


def clear_cache() -> None:
    """Drop cached service modules/scrapers (e.g. after changing the domain)."""
    with _LOCK:
        _scrapers.clear()
        _scrapper_modules.clear()
        _modules.clear()
