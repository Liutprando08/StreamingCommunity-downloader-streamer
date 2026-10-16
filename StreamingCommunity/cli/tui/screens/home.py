from __future__ import annotations

from functools import partial

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
    OptionList,
    Static,
    Tab,
    Tabs,
)

from ..global_search import SECTORS, aggregate_search, providers_for_sector
from ..providers import registry
from ..widgets import Header
from .activity import ActivityScreen
from .detail import DetailScreen
from .music import MusicScreen
from .search import SearchScreen

HOME_MARKUP = (
    "[b][#cba6f7] ██████╗ ███████╗████████╗███████╗[/]\n"
    "[b][#cba6f7]██╔═══██╗██╔════╝╚══██╔══╝██╔════╝[/]\n"
    "[b][#cba6f7]██║   ██║███████╗   ██║   █████╗  [/]\n"
    "[b][#cba6f7]██║   ██║╚════██║   ██║   ██╔══╝  [/]\n"
    "[b][#cba6f7] ██████╔╝███████║   ██║   ███████╗[/]\n"
    "[b][#cba6f7]  ╚════╝ ╚══════╝   ╚═╝   ╚══════╝[/]\n\n"
)

RESULT_COLUMNS = ("Titolo", "Tipo", "Anno", "Fonte")


class HomeScreen(Screen):
    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("a", "open_activity", "Attività"),
        ("/", "focus_search", "Cerca"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._sector = "all"
        self._query = ""
        self._results: list[tuple[object, object]] = []
        self._errors = 0
        self._search_token = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(classes="home-root"):
            with Container(id="sidebar"):
                options = [f"{p.name}" for p in registry.all()]
                options.append("Esci")
                yield OptionList(*options, id="menu-list")
            with Container(id="main-content"):
                with Vertical(id="home-top"):
                    yield Static(HOME_MARKUP, id="home-title-view")
                    with Horizontal(id="home-search-bar"):
                        yield Input(
                            placeholder="Cerca un titolo su tutti i servizi...",
                            id="home-search",
                        )
                        yield Button("Cerca", variant="primary", id="home-search-btn")
                    yield Tabs(
                        *[Tab(label, id=key) for key, label in SECTORS],
                        id="sector-tabs",
                    )
                with Horizontal(id="home-status-bar"):
                    yield LoadingIndicator(id="home-loader")
                    yield Static("", id="home-status")
                with Container(id="home-results-box"):
                    yield DataTable(id="home-results")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#home-results", DataTable)
        table.add_columns(*RESULT_COLUMNS)
        table.cursor_type = "row"
        self._show_loader(False)
        self.query_one("#home-search", Input).focus()

    # ── sidebar menu ──────────────────────────────────────────────────────
    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        providers = registry.all()
        index = event.option_index
        if index < len(providers):
            self.app.push_screen(SearchScreen(providers[index]))
        elif index == len(providers):
            self.app.push_screen(ActivityScreen())
        else:
            self.app.exit()

    # ── small helpers ─────────────────────────────────────────────────────
    def _set_status(self, text: str) -> None:
        self.query_one("#home-status", Static).update(text)

    def _show_loader(self, visible: bool) -> None:
        self.query_one("#home-loader", LoadingIndicator).styles.display = (
            "block" if visible else "none"
        )

    def _show_results(self, visible: bool) -> None:
        self.query_one("#home-results-box", Container).styles.display = (
            "block" if visible else "none"
        )

    def _sector_label(self) -> str:
        for key, label in SECTORS:
            if key == self._sector:
                return label
        return "Tutti"

    # ── global search ─────────────────────────────────────────────────────
    @on(Input.Submitted, "#home-search")
    @on(Button.Pressed, "#home-search-btn")
    def _on_search_submit(self, event) -> None:
        query = self.query_one("#home-search", Input).value.strip()
        if not query:
            self._set_status("[#f9e2af]Inserisci un titolo da cercare.")
            return
        self._start_search(query)

    def action_focus_search(self) -> None:
        self.query_one("#home-search", Input).focus()

    @on(Tabs.TabActivated)
    def _on_sector(self, event: Tabs.TabActivated) -> None:
        tab = event.tab
        if tab is None or tab.id is None:
            return
        self._sector = tab.id
        # Clicking a tab moves focus to the Tabs widget; put it back on the
        # query field so the user can type immediately.
        self.query_one("#home-search", Input).focus()
        # Re-run the current query against the newly selected sector.
        if self._query:
            self._start_search(self._query)

    def _start_search(self, query: str) -> None:
        self._query = query
        self._results = []
        self._errors = 0
        self._search_token += 1
        token = self._search_token
        table = self.query_one("#home-results", DataTable)
        table.clear()
        # Reveal the results box on the first search (hidden by default).
        self._show_results(True)
        self._set_status(
            f"[#f9e2af]Ricerca in corso · settore {self._sector_label()}..."
        )
        self._show_loader(True)
        self.run_worker(
            partial(self._run_search, query, token),
            group="global-search",
            exclusive=True,
            thread=True,
        )

    def _run_search(self, query: str, token: int) -> None:
        total = 0
        for provider, entries, error in aggregate_search(
            providers_for_sector(self._sector), query
        ):
            if error is not None:
                self.app.call_from_thread(self._note_error, token)
                continue
            if not entries:
                continue
            total += len(entries)
            self.app.call_from_thread(self._add_results, token, provider, entries)
        self.app.call_from_thread(self._finish_search, token, total)

    def _note_error(self, token: int) -> None:
        if token == self._search_token:
            self._errors += 1

    def _add_results(self, token: int, provider, entries) -> None:
        if token != self._search_token:
            return
        table = self.query_one("#home-results", DataTable)
        for entry in entries:
            index = len(self._results)
            self._results.append((provider, entry))
            table.add_row(*self._row_values(provider, entry), key=str(index))

    @staticmethod
    def _row_values(provider, entry) -> tuple[str, str, str, str]:
        name = getattr(entry, "name", "") or "?"
        media_type = getattr(entry, "type", "") or ""
        year = getattr(entry, "year", "") or ""
        return str(name), str(media_type), str(year), str(provider.name)

    def _finish_search(self, token: int, total: int) -> None:
        if token != self._search_token:
            return
        self._show_loader(False)
        if total == 0:
            message = "[#f9e2af]Nessun risultato trovato."
            if self._errors:
                message += f"  [#f38ba8]({self._errors} servizi senza risposta)[/]"
            self._set_status(message)
            return
        message = f"[#a6e3a1]{total} risultato/i. Invio per aprire."
        if self._errors:
            message += f"  [#f38ba8]({self._errors} servizi senza risposta)[/]"
        self._set_status(message)
        table = self.query_one("#home-results", DataTable)
        if table.row_count:
            table.move_cursor(row=0)

    # ── opening a result ──────────────────────────────────────────────────
    @on(DataTable.RowSelected, "#home-results")
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        try:
            index = int(str(event.row_key.value))
        except (ValueError, TypeError):
            return
        self._open_entry(index)

    def _open_entry(self, index: int) -> None:
        if index < 0 or index >= len(self._results):
            return
        provider, entry = self._results[index]
        if getattr(provider, "flow", "") == "music":
            # Hand the query to the music drill-down screen so artist/album
            # levels keep working from a global hit.
            self.app.push_screen(MusicScreen(provider, initial_query=self._query))
            return
        self.app.push_screen(
            DetailScreen(provider, entry, is_series=provider.is_series(entry))
        )

    # ── misc actions ──────────────────────────────────────────────────────
    def action_toggle_dark(self) -> None:
        app = self.app
        app.theme = "textual-dark" if app.theme == "textual-light" else "textual-light"

    def action_open_activity(self) -> None:
        self.app.push_screen(ActivityScreen())
