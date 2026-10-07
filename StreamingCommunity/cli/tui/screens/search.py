# Search screen: prompts a query, runs the provider search in a worker and
# shows the results in a table.

from __future__ import annotations

from typing import cast

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import (
    DataTable,
    Footer,
    Input,
    Label,
    LoadingIndicator,
    Static,
)

from ..providers.base import MusicProvider, ServiceProvider
from ..widgets import Header
from .detail import DetailScreen
from .music import MusicScreen


class SearchScreen(Screen):
    BINDINGS = [("escape", "back", "Indietro")]

    def __init__(self, provider: ServiceProvider, **kwargs):
        super().__init__(**kwargs)
        self.provider = provider
        self._entries = []
        self._rows = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="flow-root"):
            yield Label(
                f"[bold cyan]Search on {self.provider.name}[/]", id="search-title"
            )
            yield Input(
                placeholder="Insert the title (ex. One Piece)",
                id="search-input",
            )
            with Container(id="table-box"):
                yield DataTable(id="results")
                yield LoadingIndicator(id="search-loader")
            yield Static("", id="search-status")
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

    def _show_loader(self, visible: bool) -> None:
        self.query_one("#search-loader", LoadingIndicator).styles.display = (
            "block" if visible else "none"
        )
        self.query_one("#results", DataTable).styles.display = (
            "none" if visible else "block"
        )

    @on(Input.Submitted, "#search-input")
    def _on_submit(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if not query:
            return
        self.query_one("#search-status", Static).update("[yellow]Search ongoing...")
        self._show_loader(True)
        from functools import partial

        self.run_worker(
            partial(self._do_search, query), group="search", exclusive=True, thread=True
        )

    def _set_status(self, text: str) -> None:
        self.query_one("#search-status", Static).update(text)

    def _do_search(self, query: str) -> None:
        results = []
        try:
            results = self.provider.search(query)
        except Exception as exc:
            self.app.call_from_thread(self._set_status, f"[red]Search error: {exc}")
            self.app.call_from_thread(self._show_loader, False)
            return

        def apply(results):
            self._entries = results
            columns = self.provider.result_columns()
            table = self.query_one("#results", DataTable)
            table.clear()
            self._rows = {}
            for idx, entry in enumerate(results):
                row_key = table.add_row(
                    *[
                        str(getattr(entry, attr, "") or "")
                        for _, attr in columns
                    ],
                    key=str(idx),
                )
                self._rows[idx] = row_key
            if not results:
                self.query_one("#search-status", Static).update(
                    "[yellow]Nessun risultato trovato."
                )
            else:
                self.query_one("#search-status", Static).update(
                    f"[green]{len(results)} risultato/i trovato/i. Invio per aprire."
                )
            self._show_loader(False)

        self.app.call_from_thread(lambda: apply(results))

    @on(DataTable.RowSelected)
    def _on_select(self, event: DataTable.RowSelected) -> None:
        try:
            index = int(str(event.row_key.value))
        except (ValueError, TypeError):
            return
        if index < 0 or index >= len(self._entries):
            return
        entry = self._entries[index]
        self.app.push_screen(
            DetailScreen(self.provider, entry, is_series=self.provider.is_series(entry))
        )

    def action_back(self) -> None:
        self.app.pop_screen()

