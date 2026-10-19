# Download/stream queue: processes the items sequentially in a worker and
# reflects live progress from the shared download_tracker.
#
# Top bar has the queue title and a live overall progress summary; the table
# lists every job with its progress bar/status/speed, and a console log shows
# the underlying downloader output.

from __future__ import annotations

from typing import Any, Callable, cast

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Label,
    LoadingIndicator,
    Static,
)
from textual.widgets.data_table import RowKey

from StreamingCommunity.source.utils.tracker import download_tracker

from ..formatting import progress_bar, status_badge
from ..providers.base import (
    AnyProvider,
    MangaProtocol,
    MusicProtocol,
    SeriesFlowProvider,
    TorrentProtocol,
    VideoProtocol,
)
from ..widgets import Header
from ..workers import prepare_download_context
from .log import LogPanel

# How each queue item kind is reported to the download tracker.
MEDIA_TYPES = {
    "film": "Film",
    "episode": "Episode",
    "track": "Track",
    "album": "Album",
}


class QueueScreen(Screen):
    BINDINGS = [("escape", "back", "Indietro")]

    # Monotonic count of finished queues. A queue that dismisses itself when
    # done can complete entirely inside the click that opened it, so callers
    # (tests) watch this instead of trying to catch the transient screen.
    completed = 0

    def __init__(
        self,
        provider: AnyProvider,
        items: list[dict[str, Any]],
        title: str = "",
        on_complete: Callable[[], None] | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.provider = provider
        self.items = items
        self.title = title
        self.on_complete = on_complete

        self._id_by_row: dict[int, str | None] = {}
        self._active_row: int | None = None
        self._status_override: dict[int, str] = {}
        self._done = 0
        self._finished = False
        self._timer = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="flow-root"):
            yield Label(f"[bold #89dceb]{self.title}[/]", id="queue-title")
            yield Static("", id="queue-summary")
            with Horizontal(id="queue-actions"):
                yield Button("Annulla", variant="error", id="cancel-btn", disabled=True)
                yield Button("Torna indietro", id="back-btn")
            with Container(id="table-box"):
                yield DataTable(id="queue-table")
                yield LoadingIndicator(id="queue-loader")
            yield LogPanel(max_lines=500, auto_scroll=True, id="queue-log")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#queue-table", DataTable)
        table.add_column("▶", key="mar")
        table.add_column("Lavoro", key="job")
        table.add_column("Stato", key="status")
        table.add_column("Avanzamento", key="pct")
        table.add_column("Vel.", key="speed")
        table.add_column("Dim.", key="size")
        table.cursor_type = "row"

        for idx, item in enumerate(self.items):
            table.add_row(
                "·",
                item.get("label", "?"),
                "[dim]in coda[/dim]",
                "",
                "",
                "",
                key=idx,
            )
            self._id_by_row[idx] = None

        self.query_one("#queue-loader", LoadingIndicator).styles.display = "none"
        self._update_summary()
        self._timer = self.set_interval(0.5, self._refresh)
        self.run_worker(
            self._process_items, group="queue", exclusive=True, thread=True
        )

    def on_unmount(self) -> None:
        if self._timer is not None:
            try:
                self._timer.stop()
            except Exception:
                pass

    # ── worker ────────────────────────────────────────────────────────────
    def _process_items(self) -> None:
        for idx, item in enumerate(self.items):
            self.app.call_from_thread(self._set_active_row, idx)

            if item.get("mode") == "download":
                label = item["label"]
                media_type = MEDIA_TYPES.get(item.get("kind"), "Film")
                download_id = prepare_download_context(
                    label,
                    site=self.provider.name,
                    media_type=media_type,
                    season=item.get("season") or 0,
                    episode=item.get("episode") or 0,
                )
                self.app.call_from_thread(self._bind_id, idx, download_id)
                # Downloaders that self-register (the HLS path) open their own
                # tracker entry; torrent and single-video downloaders do not, so
                # open a fallback entry here to keep the row/activity populated.
                self._ensure_tracker_entry(download_id, label, media_type)
                try:
                    self._run_download(idx, item, download_id)
                except Exception as exc:
                    self.app.call_from_thread(
                        self._set_row_status, idx, f"errore: {exc}"
                    )
                    try:
                        download_tracker.complete_download(
                            download_id, success=False, error=str(exc)
                        )
                    except Exception:
                        pass
            else:
                self.app.call_from_thread(
                    self._set_row_status, idx, "▶ streaming..."
                )
                try:
                    self._run_stream(item)
                    self.app.call_from_thread(self._set_row_status, idx, "finito")
                except Exception as exc:
                    self.app.call_from_thread(
                        self._set_row_status, idx, f"errore: {exc}"
                    )

            self.app.call_from_thread(self._mark_done_row, idx)

        self.app.call_from_thread(self._all_done)

    @staticmethod
    def _result_path(result: Any) -> Any:
        """Normalise a downloader return value to a bare path/``None``.

        Single-video downloaders (YouTube, MostraGuarda) and a few episode
        downloaders report the outcome as a ``(path, stopped)`` tuple, returning
        a falsey path on failure. Collapsing the tuple to its path keeps the
        ``result is None`` success check below accurate.
        """
        if isinstance(result, tuple):
            return result[0] if result else None
        return result

    def _ensure_tracker_entry(
        self, download_id: str, label: str, media_type: str
    ) -> None:
        """Open a fallback tracker entry for downloaders that don't self-register.

        The HLS path registers itself (with the same id) via the N_m3u8 wrapper;
        torrent and single-video downloaders don't, so without this their row
        would stay on "avvio..." and never appear in the activity screen.
        """
        try:
            if download_id in download_tracker.downloads:
                return
            download_tracker.start_download(
                download_id, label, self.provider.name, media_type
            )
            download_tracker.update_status(download_id, "Downloading ...")
        except Exception:
            pass

    def _run_download(self, idx: int, item: dict[str, Any], download_id: str) -> None:
        # Each queue kind is handled by the provider kinds that implement it:
        # only music answers track/album, only the season flow answers
        # episodes, and every kind but music can carry a single film entry.
        kind = item.get("kind")
        if kind == "film":
            provider = cast(
                VideoProtocol | TorrentProtocol | MangaProtocol, self.provider
            )
            # Also the atomic (torrent) entry point: the provider routes to the
            # movie or series folder itself.
            result = self._result_path(provider.download_film(item["entry"]))
            self._maybe_dub(idx, item, result)
        elif kind == "track":
            provider = cast(MusicProtocol, self.provider)
            result = self._result_path(provider.download_track(item["entry"]))
        elif kind == "album":
            provider = cast(MusicProtocol, self.provider)
            result = provider.download_album(item["entry"])
        else:
            provider = cast(SeriesFlowProvider, self.provider)
            result = self._result_path(
                provider.download_episode(
                    item["obj_episode"],
                    item["season"],
                    item["episode"],
                    item["scraper"],
                )
            )

        failed = result is None or (kind == "album" and result is False)
        if failed:
            try:
                download_tracker.complete_download(
                    download_id, success=False, error="Nessun output prodotto"
                )
            except Exception:
                pass
            return

        # Downloaders that self-register (HLS) have already closed their entry,
        # which makes this a no-op; the rest only have the fallback entry opened
        # by ``_ensure_tracker_entry``, so close it here.
        try:
            if download_id in download_tracker.downloads:
                download_tracker.complete_download(
                    download_id,
                    success=True,
                    path=result if isinstance(result, str) else None,
                )
        except Exception:
            pass

    def _maybe_dub(self, idx: int, item: dict[str, Any], video_path: Any) -> None:
        """Mux the Italian audio picked before enqueueing, if any.

        Runs after a successful torrent download. ``video_path`` is the file
        returned by the torrent downloader. A failure here is non-fatal: the
        torrent itself already downloaded fine.
        """
        source = item.get("dub_entry")
        if source is None or not video_path:
            return
        dub = getattr(self.provider, "dub_audio", None)
        if not callable(dub):
            return

        self.app.call_from_thread(
            self._set_status_override, idx, "[#f9e2af]audio ITA..."
        )
        try:
            dubbed = dub(item["entry"], str(video_path), source)
        except Exception as exc:
            self.app.call_from_thread(
                self._set_status_override, idx, f"[#f38ba8]dub errore: {exc}"
            )
            return
        if dubbed:
            self.app.call_from_thread(
                self._set_status_override, idx, "[#a6e3a1]audio ITA ✓"
            )
        else:
            self.app.call_from_thread(
                self._set_status_override, idx, "[#f9e2af]dub non riuscito"
            )

    def _run_stream(self, item: dict[str, Any]) -> None:
        # Streaming is only offered by the video catalogs; manga implements the
        # entry points as "never offered" no-ops.
        provider = cast(SeriesFlowProvider, self.provider)
        if item.get("kind") == "film":
            provider.stream_film(item["entry"])
        else:
            provider.stream_episode(
                item["obj_episode"],
                item["season"],
                item["episode"],
                item["scraper"],
            )

    # ── UI updates (always called from the message thread) ────────────────
    def _set_active_row(self, idx: int) -> None:
        # The worker keeps running after the screen is popped, so every UI
        # callback must tolerate being invoked on an unmounted screen.
        if not self.is_mounted:
            return
        table = self.query_one("#queue-table", DataTable)
        if self._active_row is not None:
            table.update_cell(RowKey(self._active_row), "mar", "·")
        self._active_row = idx
        table.update_cell(RowKey(idx), "mar", "▶")
        self.query_one("#cancel-btn", Button).disabled = False

    def _bind_id(self, idx: int, download_id: str) -> None:
        self._id_by_row[idx] = download_id
        self._set_row_status(idx, "avvio...")

    def _set_row_status(self, idx: int, text: str) -> None:
        if not self.is_mounted:
            return
        self.query_one("#queue-table", DataTable).update_cell(
            RowKey(idx), "status", text
        )

    def _set_status_override(self, idx: int, text: str) -> None:
        """Status that wins over the tracker polling (used during the dub)."""
        self._status_override[idx] = text
        self._set_row_status(idx, text)

    def _mark_done_row(self, idx: int) -> None:
        if not self.is_mounted:
            return
        table = self.query_one("#queue-table", DataTable)
        did = self._id_by_row.get(idx)
        marker = "✓"
        if did:
            for h in download_tracker.get_history():
                if h.get("id") == did and h.get("status") in ("failed", "cancelled"):
                    marker = "✗"
                    break
        table.update_cell(RowKey(idx), "mar", marker)
        self._done += 1
        self._update_summary()

    def _all_done(self) -> None:
        if self._finished:
            return
        self._finished = True
        QueueScreen.completed += 1
        if self.is_mounted:
            self.query_one("#cancel-btn", Button).disabled = True
            self.query_one("#queue-loader", LoadingIndicator).styles.display = "none"
            total = len(self.items)
            self.query_one("#queue-title", Label).update(
                f"[bold #a6e3a1]{self.title}[/] · completato ({total}/{total})"
            )
            self._update_summary()
        # Still fire the completion callback even if the user navigated away,
        # so a multi-season batch keeps walking its queue.
        if self.on_complete is not None:
            self.on_complete()

    def _update_summary(self) -> None:
        if not self.is_mounted:
            return
        total = len(self.items)
        percent = (self._done / total * 100.0) if total else 0.0
        jobs = "lavoro" if total == 1 else "lavori"
        if self._finished:
            state = "completato" if total == 1 else "completati"
        else:
            state = "in corso"
        self.query_one("#queue-summary", Static).update(
            f"{progress_bar(percent)}   "
            f"[dim]{self._done}/{total} {jobs} {state}[/]"
        )

    def _refresh(self) -> None:
        active = download_tracker.get_active_downloads()
        history = download_tracker.get_history()
        active_by_id = {d.get("id"): d for d in active}
        history_by_id = {d.get("id"): d for d in history}

        table = self.query_one("#queue-table", DataTable)
        for idx, did in list(self._id_by_row.items()):
            if not did:
                continue
            info = active_by_id.get(did)
            if info is None:
                info = history_by_id.get(did)
                if info is None:
                    continue
                status = info.get("status", "done")
                table.update_cell(
                    RowKey(idx),
                    "status",
                    self._status_override.get(idx) or status_badge(status),
                )
                table.update_cell(
                    RowKey(idx), "pct", progress_bar(info.get("progress", 0))
                )
            else:
                table.update_cell(
                    RowKey(idx),
                    "status",
                    self._status_override.get(idx)
                    or status_badge(info.get("status")),
                )
                table.update_cell(
                    RowKey(idx), "pct", progress_bar(info.get("progress", 0))
                )
                table.update_cell(RowKey(idx), "speed", str(info.get("speed", "")))
                table.update_cell(RowKey(idx), "size", str(info.get("size", "")))

        self.query_one("#queue-log", LogPanel).drain_console()

    # ── actions ───────────────────────────────────────────────────────────
    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self) -> None:
        if self._active_row is None:
            return
        did = self._id_by_row.get(self._active_row)
        if did:
            download_tracker.request_stop(did)
            self._set_row_status(self._active_row, "annullo...")

    @on(Button.Pressed, "#back-btn")
    def _back(self) -> None:
        self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()