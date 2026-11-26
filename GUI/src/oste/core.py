"""Glue between the Flet interface and the StreamingCommunity core.

The core package is imported lazily so the interface can still start (and show
a helpful error) when it is not installed, e.g. while building the APK.
"""

# Tracker/downloader probes fail soft on purpose.
# ruff: noqa: BLE001, S110

from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

# ── provider helpers ───────────────────────────────────────────────────────
_ICON_BY_ALIAS = {
    "streamingcommunity": "MOVIE",
    "altadefinizione": "THEATERS",
    "animeunity": "ANIMATION",
    "animeworld": "ANIMATION",
    "mangaworld": "MENU_BOOK",
    "zlibrary": "LOCAL_LIBRARY",
    "torrent": "DOWNLOAD",
    "musicmp3": "MUSIC_NOTE",
    "goldenmp3": "MUSIC_NOTE",
    "monochrome": "HEADPHONES",
    "youtube": "SMART_DISPLAY",
    "raiplay": "LIVE_TV",
    "mediasetinfinity": "VIDEO_LIBRARY",
    "crunchyroll": "ANIMATION",
    "plutotv": "TV",
}

_CATEGORY_ICON = {
    "Film": "MOVIE",
    "Film_Serie": "MOVIE",
    "Serie": "TV",
    "Anime": "ANIMATION",
    "Music": "MUSIC_NOTE",
    "Books": "LOCAL_LIBRARY",
    "Manga": "MENU_BOOK",
}


def _flet_icon(name: str):
    import flet as ft

    return getattr(ft.Icons, name, ft.Icons.CATEGORY)


def registry():
    """Return the provider registry from the TUI layer (imported lazily)."""
    from StreamingCommunity.cli.tui.providers import registry as _registry

    return _registry


def all_providers() -> list[Any]:
    return list(registry().all())


def provider_icon(provider: Any):
    alias = str(getattr(provider, "alias", "") or "")
    name = _ICON_BY_ALIAS.get(alias)
    if name is None:
        name = _CATEGORY_ICON.get(str(getattr(provider, "category", "")), "CATEGORY")
    return _flet_icon(name)


def provider_kind_label(provider: Any) -> str:
    alias = str(getattr(provider, "alias", "") or "")
    flow = str(getattr(provider, "flow", "") or "")
    category = str(getattr(provider, "category", "") or "")
    if alias == "torrent":
        return "Torrent"
    if flow == "music":
        return "Musica"
    if category == "Books":
        return "Libri"
    if category == "Manga":
        return "Manga"
    if flow == "atomic":
        return "Video singolo"
    return category.replace("_", " ") or "Video"


def entry_name(entry: Any) -> str:
    for attr in ("name", "title", "series_name", "manga_name"):
        value = getattr(entry, attr, None)
        if value:
            return str(value)
    return "Sconosciuto"


def entry_subtitle(provider: Any, entry: Any) -> str:
    parts: list[str] = []
    try:
        columns = provider.result_columns()
    except Exception:
        columns = ()
    for header, attr in columns:
        if attr in ("name", "title"):
            continue
        value = getattr(entry, attr, None)
        if value in (None, "", 0, "0"):
            continue
        parts.append(f"{header}: {value}")
        if len(parts) >= 3:
            break
    return " · ".join(parts)


def entry_pairs(provider: Any, entry: Any) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    try:
        columns = provider.result_columns()
    except Exception:
        columns = ()
    for header, attr in columns:
        if attr in ("name", "title"):
            continue
        value = getattr(entry, attr, None)
        if value in (None, "", 0, "0"):
            continue
        pairs.append((str(header), str(value)))
    return pairs


def media_badge(provider: Any, is_series: bool) -> tuple[str, str]:
    if is_series:
        return (
            getattr(provider, "series_icon", "📺"),
            getattr(provider, "series_label", "Serie"),
        )
    return (
        getattr(provider, "film_icon", "🎬"),
        getattr(provider, "film_label", "Film"),
    )


def format_number(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return str(number)


def to_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def core_version() -> str:
    try:
        from StreamingCommunity.upload.version import __version__

        return str(__version__)
    except Exception:
        return "n/d"


def config_manager():
    from StreamingCommunity.utils import config_manager as manager

    return manager


# ── download queue ─────────────────────────────────────────────────────────
MEDIA_TYPES = {
    "film": "Film",
    "episode": "Episode",
    "track": "Track",
    "album": "Album",
    "book": "Book",
}

_FINISHED = {"done", "failed", "cancelled"}


@dataclass
class Job:
    id: str
    label: str
    provider: Any
    kind: str
    mode: str = "download"
    entry: Any = None
    obj_episode: Any = None
    season: int = 0
    episode: int = 0
    scraper: Any = None
    status: str = "queued"
    error: str | None = None
    tracker_id: str | None = None
    result_path: str | None = None
    created: float = field(default_factory=time.time)
    finished: float | None = None


class DownloadManager:
    """A tiny sequential download queue running outside the UI thread.

    The heavy downloaders live in the core package; this class only calls them
    from a dedicated worker thread, prepares the shared ``context_tracker`` and
    exposes a snapshot the Flet view can poll for progress.
    """

    def __init__(self) -> None:
        self._jobs: list[Job] = []
        self._lock = threading.RLock()
        self._queue: queue.Queue[Job | None] = queue.Queue()
        self._worker: threading.Thread | None = None

    # ── public API ────────────────────────────────────────────────────────
    def enqueue(self, provider: Any, items: list[dict[str, Any]]) -> list[Job]:
        created: list[Job] = []
        for item in items:
            created.append(
                Job(
                    id=uuid.uuid4().hex[:10],
                    label=str(item.get("label") or "Download"),
                    provider=provider,
                    kind=str(item.get("kind") or "film"),
                    mode=str(item.get("mode") or "download"),
                    entry=item.get("entry"),
                    obj_episode=item.get("obj_episode"),
                    season=to_int(item.get("season"), 0),
                    episode=to_int(item.get("episode"), 0),
                    scraper=item.get("scraper"),
                )
            )
        if not created:
            return created
        with self._lock:
            self._jobs.extend(created)
            for job in created:
                self._queue.put(job)
            self._ensure_worker_locked()
        return created

    def cancel(self, job_id: str) -> None:
        with self._lock:
            job = next((item for item in self._jobs if item.id == job_id), None)
        if job is None or job.status in _FINISHED:
            return
        if job.tracker_id:
            try:
                from StreamingCommunity.source.utils.tracker import download_tracker

                download_tracker.request_stop(job.tracker_id)
            except Exception:
                pass
        job.status = "cancelling" if job.status == "running" else "cancelled"

    def clear_finished(self) -> None:
        with self._lock:
            self._jobs = [job for job in self._jobs if job.status not in _FINISHED]

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs)
        try:
            from StreamingCommunity.source.utils.tracker import download_tracker

            downloads = download_tracker.downloads
        except Exception:
            downloads = {}

        result: list[dict[str, Any]] = []
        for job in jobs:
            tracker = None
            if job.tracker_id:
                raw = downloads.get(job.tracker_id)
                if raw:
                    try:
                        tracker = dict(raw)
                    except Exception:
                        tracker = None
            result.append(
                {
                    "id": job.id,
                    "label": job.label,
                    "kind": job.kind,
                    "mode": job.mode,
                    "status": job.status,
                    "error": job.error,
                    "result_path": job.result_path,
                    "provider": getattr(job.provider, "name", ""),
                    "tracker": tracker,
                }
            )
        return result

    # ── worker plumbing ───────────────────────────────────────────────────
    def _ensure_worker_locked(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._worker = threading.Thread(
            target=self._loop, name="oste-downloads", daemon=True
        )
        self._worker.start()

    def _loop(self) -> None:
        while True:
            job = self._queue.get()
            if job is None:
                return
            if job.status == "cancelled":
                continue
            self._run(job)

    def _run(self, job: Job) -> None:
        job.status = "running"
        try:
            if job.mode == "stream":
                self._stream(job)
                job.status = "done"
            else:
                self._download(job)
                job.status = "done"
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc) or exc.__class__.__name__
        finally:
            job.finished = time.time()

    def _stream(self, job: Job) -> None:
        if job.kind == "film":
            job.provider.stream_film(job.entry)
        else:
            job.provider.stream_episode(
                job.obj_episode, job.season, job.episode, job.scraper
            )

    def _download(self, job: Job) -> None:
        from StreamingCommunity.cli.tui.workers import prepare_download_context
        from StreamingCommunity.source.utils.tracker import download_tracker

        site = str(getattr(job.provider, "name", "") or "?")
        media_type = MEDIA_TYPES.get(job.kind, "Film")
        download_id = prepare_download_context(
            job.label,
            site=site,
            media_type=media_type,
            season=job.season,
            episode=job.episode,
        )
        job.tracker_id = download_id

        if download_id not in download_tracker.downloads:
            download_tracker.start_download(download_id, job.label, site, media_type)
            download_tracker.update_status(download_id, "Downloading ...")

        try:
            result = self._dispatch(job)
        except Exception as exc:
            try:
                download_tracker.complete_download(
                    download_id, success=False, error=str(exc)
                )
            except Exception:
                pass
            raise

        path = result[0] if isinstance(result, tuple) else result
        failed = path is None or (job.kind == "album" and result is False)
        if failed:
            try:
                download_tracker.complete_download(
                    download_id, success=False, error="Nessun output prodotto"
                )
            except Exception:
                pass
            raise RuntimeError("Nessun output prodotto")

        if isinstance(path, str):
            job.result_path = path
        try:
            if download_id in download_tracker.downloads:
                download_tracker.complete_download(
                    download_id,
                    success=True,
                    path=path if isinstance(path, str) else None,
                )
        except Exception:
            pass

    @staticmethod
    def _dispatch(job: Job) -> Any:
        kind = job.kind
        if kind == "film":
            return job.provider.download_film(job.entry)
        if kind == "track":
            return job.provider.download_track(job.entry)
        if kind == "album":
            return job.provider.download_album(job.entry)
        if kind == "book":
            return job.provider.download_book(job.entry)
        return job.provider.download_episode(
            job.obj_episode, job.season, job.episode, job.scraper
        )


def job_status_text(job: dict[str, Any]) -> str:
    tracker = job.get("tracker") or {}
    raw = str(tracker.get("status") or job.get("status") or "").lower()
    if "cancel" in raw:
        return "Annullamento…"
    if "fail" in raw or "error" in raw:
        return "Errore"
    if "complet" in raw or "done" in raw:
        return "Completato"
    if job.get("status") == "queued":
        return "In coda"
    if job.get("status") == "done":
        return "Completato"
    if job.get("status") == "failed":
        return "Errore"
    if job.get("status") == "cancelled":
        return "Annullato"
    if job.get("mode") == "stream":
        return "Streaming…"
    return "In corso…"


def job_progress(job: dict[str, Any]) -> float:
    if job.get("status") == "done":
        return 1.0
    tracker = job.get("tracker") or {}
    try:
        value = float(tracker.get("progress") or 0.0)
    except (TypeError, ValueError):
        value = 0.0
    return max(0.0, min(1.0, value / 100.0))


def job_meta(job: dict[str, Any]) -> str:
    if job.get("error"):
        return str(job["error"])
    if job.get("result_path"):
        return str(job["result_path"])
    tracker = job.get("tracker") or {}
    bits = [str(tracker.get(key) or "") for key in ("speed", "size")]
    return " · ".join(bit for bit in bits if bit)
