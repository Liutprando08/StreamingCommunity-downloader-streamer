# Search screen: prompts a query, runs the provider search in a worker and
# shows the results in a table.

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input, Label, LoadingIndicator, Static

from ..providers.base import ServiceProvider
from .detail import DetailScreen


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
            yield Label(f"[bold cyan]Ricerca su {self.provider.name}[/]", id="search-title")
            yield Input(
                placeholder="Inserisci il titolo da cercare (es. One Piece)",
                id="search-input",
            )
            with Container(id="table-box"):
                yield DataTable(id="results")
                yield LoadingIndicator(id="search-loader")
            yield Static("", id="search-status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#results", DataTable)
        table.add_columns("Nome", "Tipo", "Anno", "IMDB")
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
        self.query_one("#search-status", Static).update("[yellow]Ricerca in corso...")
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
            self.app.call_from_thread(self._set_status, f"[red]Errore ricerca: {exc}")
            self.app.call_from_thread(self._show_loader, False)
            return

        def apply(results):
            self._entries = results
            table = self.query_one("#results", DataTable)
            table.clear()
            self._rows = {}
            for idx, entry in enumerate(results):
                row_key = table.add_row(
                    getattr(entry, "name", "") or "",
                    str(getattr(entry, "type", "") or ""),
                    str(getattr(entry, "year", "") or ""),
                    str(getattr(entry, "imdb_id", "") or ""),
                    key=idx,
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