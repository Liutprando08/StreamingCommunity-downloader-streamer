# Search screen: query bar on top, results on the left and a live metadata
# preview card on the right (VibraVid-style split layout).

from __future__ import annotations

from functools import partial
from typing import cast

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Input,
    LoadingIndicator,
    Static,
)

from ..formatting import media_badge, preview_card
from ..providers.base import MusicProvider, ServiceProvider, TorrentProvider
from ..widgets import Header
from .detail import DetailScreen
from .music import MusicScreen

INITIAL_PREVIEW = (
    "[dim]Cerca un titolo, poi sposta il cursore sui risultati "
    "per vedere qui i dettagli.[/]"
)


class SearchScreen(Screen):
    BINDINGS = [("escape", "back", "Indietro")]

    def __init__(
        self, provider: ServiceProvider | MusicProvider | TorrentProvider, **kwargs
    ):
        super().__init__(**kwargs)
        self.provider = provider
        self._entries = []
        self._highlighted: int | None = None

    def compose(self) -> ComposeResult:
        name = self.provider.name
        yield Header()
        with Vertical(classes="flow-root"):
            yield Static(f"[bold #89dceb]Search on {name}[/]", id="search-title")
            with Horizontal(id="search-inputs-bar"):
                yield Input(
                    placeholder="Insert the title (ex. One Piece)",
                    id="search-input",
                )
                yield Button("Cerca", variant="primary", id="search-btn")
            yield Static("", id="search-status")
            with Horizontal(id="search-split"):
                with Container(id="table-box"):
                    yield DataTable(id="results")
                    yield LoadingIndicator(id="search-loader")
                with Vertical(id="preview-container"):
                    with Vertical(id="preview-box"):
                        yield Static(INITIAL_PREVIEW, id="search-preview")
                    with Horizontal(id="preview-actions"):
                        yield Button("Apri", variant="primary", id="preview-open-btn")
        yield Footer()

    def on_mount(self) -> None:
        # Music providers have their own mode/drill-down screen.
        if getattr(self.provider, "flow", "episode") == "music":
            # switch_screen replaces SearchScreen; push+pop would pop the
            # MusicScreen we just pushed.
            provider = cast(MusicProvider, self.provider)
            self.app.switch_screen(MusicScreen(provider))
            return

        table = self.query_one("#results", DataTable)
        columns = self.provider.result_columns()
        table.add_columns(*[header for header, _attr in columns])
        table.cursor_type = "row"
        self._show_loader(False)
        self.query_one("#search-input", Input).focus()

    def _show_loader(self, visible: bool) -> None:
        self.query_one("#search-loader", LoadingIndicator).styles.display = (
            "block" if visible else "none"
        )
        self.query_one("#results", DataTable).styles.display = (
            "none" if visible else "block"
        )

    def _set_status(self, text: str) -> None:
        self.query_one("#search-status", Static).update(text)

    def _set_preview(self, text: str) -> None:
        self.query_one("#search-preview", Static).update(text)

    # ── searching ─────────────────────────────────────────────────────────
    @on(Input.Submitted, "#search-input")
    @on(Button.Pressed, "#search-btn")
    def _on_submit(self, event) -> None:
        query = self.query_one("#search-input", Input).value.strip()
        if not query:
            self._set_status("[#f9e2af]Inserisci un titolo da cercare.")
            return
        self._set_status("[#f9e2af]Search ongoing...")
        self._set_preview(INITIAL_PREVIEW)
        self._highlighted = None
        self._show_loader(True)
        self.run_worker(
            partial(self._do_search, query), group="search", exclusive=True, thread=True
        )

    def _do_search(self, query: str) -> None:
        results = []
        try:
            results = self.provider.search(query)
        except Exception as exc:
            self.app.call_from_thread(self._set_status, f"[#f38ba8]Search error: {exc}")
            self.app.call_from_thread(self._show_loader, False)
            return

        def apply(results):
            self._entries = results
            columns = self.provider.result_columns()
            table = self.query_one("#results", DataTable)
            table.clear()
            for idx, entry in enumerate(results):
                table.add_row(
                    *[str(getattr(entry, attr, "") or "") for _, attr in columns],
                    key=str(idx),
                )
            self._show_loader(False)
            if not results:
                self._set_status("[#f9e2af]Nessun risultato trovato.")
                self._set_preview(INITIAL_PREVIEW)
                return
            self._set_status(
                f"[#a6e3a1]{len(results)} risultato/i trovato/i. Invio per aprire."
            )
            # Highlight the first hit so the preview card is populated right away.
            table.move_cursor(row=0)
            self._show_preview(0)

        self.app.call_from_thread(lambda: apply(results))

    # ── preview card ──────────────────────────────────────────────────────
    @on(DataTable.RowHighlighted, "#results")
    def _on_highlighted(self, event: DataTable.RowHighlighted) -> None:
        try:
            index = int(str(event.row_key.value))
        except (ValueError, TypeError):
            return
        self._show_preview(index)

    def _show_preview(self, index: int) -> None:
        if index < 0 or index >= len(self._entries):
            return
        self._highlighted = index
        entry = self._entries[index]
        self._set_preview(self._render_preview(entry))

    def _render_preview(self, entry) -> str:
        name = getattr(entry, "name", "") or "?"
        try:
            is_series = bool(self.provider.is_series(entry))
        except Exception:
            is_series = True
        icon, kind = media_badge(self.provider, is_series)

        details = (
            (header, getattr(entry, attr, ""))
            for header, attr in self.provider.result_columns()
            if attr != "name"
        )
        return preview_card(
            name,
            badges=(
                f"{icon} [bold #a6e3a1]{kind}[/]   "
                f"[dim]Fonte:[/] [#89dceb]{self.provider.name}[/]"
            ),
            details=details,
        )

    # ── opening a result ──────────────────────────────────────────────────
    @on(DataTable.RowSelected, "#results")
    def _on_select(self, event: DataTable.RowSelected) -> None:
        try:
            index = int(str(event.row_key.value))
        except (ValueError, TypeError):
            return
        self._open_entry(index)

    @on(Button.Pressed, "#preview-open-btn")
    def _open_highlighted(self) -> None:
        if self._highlighted is not None:
            self._open_entry(self._highlighted)

    def _open_entry(self, index: int) -> None:
        if index < 0 or index >= len(self._entries):
            return
        entry = self._entries[index]
        self.app.push_screen(
            DetailScreen(self.provider, entry, is_series=self.provider.is_series(entry))
        )

    def action_back(self) -> None:
        self.app.pop_screen()
