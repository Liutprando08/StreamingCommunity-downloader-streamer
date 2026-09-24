# Download/stream queue: processes the items sequentially in a worker and
# reflects live progress from the shared download_tracker.

from __future__ import annotations

from typing import Any, Callable

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Label,
    LoadingIndicator,
)
from textual.widgets.data_table import RowKey

from StreamingCommunity.source.utils.tracker import download_tracker

from ..providers.base import ServiceProvider
from ..workers import prepare_download_context
from .log import LogPanel


class QueueScreen(Screen):
    BINDINGS = [("escape", "back", "Indietro")]

    def __init__(
        self,
        provider: ServiceProvider,
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
        self._finished = False
        self._timer = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="flow-root"):
            yield Label(f"[bold cyan]{self.title}[/]", id="queue-title")
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
        table.add_column("%", key="pct")
        table.add_column("Vel.", key="speed")
        table.add_column("Dim.", key="size")
        table.cursor_type = "row"

        for idx, item in enumerate(self.items):
            table.add_row(
                "·",
                item.get("label", "?"),
                "in coda",
                "",
                "",
                "",
                key=idx,
            )
            self._id_by_row[idx] = None

        self.query_one("#queue-loader", LoadingIndicator).styles.display = "none"
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
                media_type = "Episode" if item.get("kind") == "episode" else "Film"
                download_id = prepare_download_context(
                    label,
                    site=self.provider.name,
                    media_type=media_type,
                    season=item.get("season") or 0,
                    episode=item.get("episode") or 0,
                )
                self.app.call_from_thread(self._bind_id, idx, download_id)
                try:
                    self._run_download(item, download_id)
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

    def _run_download(self, item: dict[str, Any], download_id: str) -> None:
        if item.get("kind") == "film":
            result = self.provider.download_film(item["entry"])
        else:
            result = self.provider.download_episode(
                item["obj_episode"],
                item["season"],
                item["episode"],
                item["scraper"],
            )
        # HLS.start() already records completion in download_tracker; only a
        # None return (nothing produced) needs an explicit failure here.
        if result is None:
            try:
                download_tracker.complete_download(
                    download_id, success=False, error="Nessun output prodotto"
                )
            except Exception:
                pass

    def _run_stream(self, item: dict[str, Any]) -> None:
        if item.get("kind") == "film":
            self.provider.stream_film(item["entry"])
        else:
            self.provider.stream_episode(
                item["obj_episode"],
                item["season"],
                item["episode"],
                item["scraper"],
            )

    # ── UI updates (always called from the message thread) ────────────────
    def _set_active_row(self, idx: int) -> None:
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
        self.query_one("#queue-table", DataTable).update_cell(RowKey(idx), "status", text)

    def _mark_done_row(self, idx: int) -> None:
        table = self.query_one("#queue-table", DataTable)
        did = self._id_by_row.get(idx)
        marker = "✓"
        if did:
            for h in download_tracker.get_history():
                if h.get("id") == did and h.get("status") in ("failed", "cancelled"):
                    marker = "✗"
                    break
        table.update_cell(RowKey(idx), "mar", marker)

    def _all_done(self) -> None:
        self._finished = True
        self.query_one("#cancel-btn", Button).disabled = True
        self.query_one("#queue-loader", LoadingIndicator).styles.display = "none"
        total = len(self.items)
        self.query_one("#queue-title", Label).update(
            f"[bold green]{self.title}[/] · completato ({total}/{total})"
        )
        if self.on_complete is not None:
            self.on_complete()

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
                table.update_cell(RowKey(idx), "status", str(status))
                table.update_cell(RowKey(idx), "pct", str(info.get("progress", "")))
            else:
                table.update_cell(RowKey(idx), "status", str(info.get("status", "")))
                table.update_cell(RowKey(idx), "pct", str(info.get("progress", "")))
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