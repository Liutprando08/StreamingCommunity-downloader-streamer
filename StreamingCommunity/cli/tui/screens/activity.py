# Activity screen: a live view of the shared download tracker.
#
# Two tables (active downloads + finished history) refreshed on a timer, with
# a cancel action for the highlighted download and a history clear.

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Label, Static
from textual.widgets.data_table import RowKey

from StreamingCommunity.source.utils.tracker import download_tracker

from ..formatting import format_time, progress_bar, status_badge
from ..widgets import Header


class ActivityScreen(Screen):
    BINDINGS = [("escape", "back", "Indietro")]

    REFRESH_SECONDS = 0.5

    ACTIVE_COLUMNS = (
        "Stato",
        "Titolo",
        "Fonte",
        "Tipo",
        "Avanzamento",
        "Velocità",
        "Dimensione",
    )
    HISTORY_COLUMNS = ("Esito", "Titolo", "Tipo", "Dimensione", "Fine", "Percorso")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._active_ids: list[str] = []
        self._active_signature: tuple = ()
        self._history_signature: tuple | None = ()
        self._active_highlight: str | None = None
        self._timer = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="flow-root"):
            yield Label("[bold #89dceb]Attività[/]", id="activity-title")
            yield Label("Download attivi", classes="activity-heading")
            with Container(classes="activity-box"):
                yield DataTable(id="active-table")
            yield Label("Cronologia", classes="activity-heading")
            with Container(classes="activity-box"):
                yield DataTable(id="history-table")
            with Horizontal(id="activity-actions"):
                yield Button("Annulla selezionato", variant="error", id="cancel-btn")
                yield Button("Pulisci cronologia", id="clear-btn")
                yield Button("Indietro", id="back-btn")
            yield Static("", id="activity-status")
        yield Footer()

    def on_mount(self) -> None:
        active = self.query_one("#active-table", DataTable)
        active.add_columns(*self.ACTIVE_COLUMNS)
        active.cursor_type = "row"

        history = self.query_one("#history-table", DataTable)
        history.add_columns(*self.HISTORY_COLUMNS)
        history.cursor_type = "row"

        self._timer = self.set_interval(self.REFRESH_SECONDS, self._refresh)
        self._refresh()

    def on_unmount(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    # ── refreshing ────────────────────────────────────────────────────────
    def _refresh(self) -> None:
        active = self._refresh_active()
        history = self._refresh_history()
        self._set_status(
            f"[dim]{len(active)} download attivi · {len(history)} in cronologia[/]"
        )

    def _refresh_active(self) -> list[dict]:
        downloads = download_tracker.get_active_downloads()
        signature = tuple(
            (
                str(download.get("id", "")),
                str(download.get("status", "")),
                download.get("progress"),
                str(download.get("speed", "")),
                str(download.get("size", "")),
            )
            for download in downloads
        )
        # Rebuilding the table every tick would steal the user's cursor, so
        # only touch the DOM when something actually changed.
        if signature == self._active_signature:
            return downloads
        self._active_signature = signature

        self._active_ids = [str(download.get("id", "")) for download in downloads]
        table = self.query_one("#active-table", DataTable)
        table.clear()
        seen: set[str] = set()
        for index, download in enumerate(downloads):
            # Row keys must be unique: a missing/duplicated id (possible in a
            # hand-edited or legacy tracker dump) falls back to an index key.
            raw = str(download.get("id", "") or "")
            key = raw if raw and raw not in seen else f"{raw or 'row'}__{index}"
            seen.add(key)
            table.add_row(
                status_badge(download.get("status")),
                str(download.get("title", "") or "?"),
                str(download.get("site", "") or ""),
                str(download.get("type", "") or ""),
                progress_bar(download.get("progress", 0)),
                str(download.get("speed", "") or ""),
                str(download.get("size", "") or ""),
                key=key,
            )
        self._restore_cursor(table, self._active_highlight)
        return downloads

    def _refresh_history(self) -> list[dict]:
        entries = download_tracker.get_history()
        signature = tuple(
            (
                str(entry.get("id", "")),
                str(entry.get("status", "")),
                entry.get("end_time"),
            )
            for entry in entries
        )
        if signature == self._history_signature:
            return entries
        self._history_signature = signature

        table = self.query_one("#history-table", DataTable)
        table.clear()
        for index, entry in enumerate(entries):
            # Index keys: history rows are never selected, and legacy entries
            # may share an id or omit it entirely.
            table.add_row(
                status_badge(entry.get("status")),
                str(entry.get("title", "") or "?"),
                str(entry.get("type", "") or ""),
                str(entry.get("size", "") or ""),
                format_time(entry.get("end_time")),
                str(entry.get("path", "") or ""),
                key=str(index),
            )
        return entries

    @staticmethod
    def _restore_cursor(table: DataTable, key: str | None) -> None:
        if not key:
            return
        try:
            index = table.get_row_index(RowKey(key))
        except Exception:
            return
        try:
            table.move_cursor(row=index)
        except Exception:
            pass

    def _set_status(self, text: str) -> None:
        self.query_one("#activity-status", Static).update(text)

    # ── actions ───────────────────────────────────────────────────────────
    @on(DataTable.RowHighlighted, "#active-table")
    def _on_active_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._active_highlight = str(event.row_key.value)

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self) -> None:
        index = self.query_one("#active-table", DataTable).cursor_row
        if not self._active_ids or not 0 <= index < len(self._active_ids):
            self._set_status("[#f9e2af]Nessun download attivo selezionato.")
            return
        download_id = self._active_ids[index]
        download_tracker.request_stop(download_id)
        self._refresh()
        self._set_status(
            f"[#f9e2af]Annullamento richiesto per {download_id[:8]}…[/]"
        )

    @on(Button.Pressed, "#clear-btn")
    def _clear_history(self) -> None:
        download_tracker.clear_history()
        # ``None`` can never equal a real (possibly empty) signature, so the
        # next refresh is forced to rebuild the now-empty table.
        self._history_signature = None
        self._refresh()
        self._set_status("[#a6e3a1]Cronologia svuotata.[/]")

    @on(Button.Pressed, "#back-btn")
    def _on_back_button(self) -> None:
        self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()
