# Season selection: multi-select table, then a batch starts walking
# season-by-season through the episodes screen.

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    LoadingIndicator,
    Static,
)
from textual.widgets.data_table import RowKey

from ..flow import SeasonBatch
from ..parse import parse_ranges
from ..providers.base import ServiceProvider
from .episodes import EpisodesScreen


class SeasonsScreen(Screen):
    BINDINGS = [("escape", "back", "Indietro")]

    def __init__(self, provider: ServiceProvider, entry, mode: str = "download", **kwargs):
        super().__init__(**kwargs)
        self.provider = provider
        self.entry = entry
        self.mode = mode
        self._scraper = None
        self._seasons = []
        self._selected: set[int] = set()

    def compose(self) -> ComposeResult:
        name = getattr(self.entry, "name", "") or "Sconosciuto"
        yield Header()
        with Vertical(classes="flow-root"):
            yield Label(
                f"[bold magenta]{name}[/] · [cyan]Stagioni[/]",
                id="seasons-title",
            )
            with Container(id="table-box"):
                yield DataTable(id="season-table")
                yield LoadingIndicator(id="seasons-loader")
            with Horizontal(id="seasons-actions"):
                yield Input(
                    placeholder="Range stagioni es. 1,3-5,*",
                    id="season-range",
                )
                yield Button("Seleziona tutto", id="select-all")
                yield Button("Deseleziona", id="select-none")
                yield Button("Conferma", variant="primary", id="confirm-btn")
                yield Button("Indietro", id="back-btn")
            yield Static("", id="seasons-status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#season-table", DataTable)
        table.add_column("Sel", key="sel")
        table.add_column("Stagione", key="number")
        table.add_column("Nome", key="name")
        table.cursor_type = "row"
        self._show_loader(True)
        from functools import partial
        self.run_worker(partial(self._load_seasons), group="seasons", exclusive=True, thread=True)

    def _show_loader(self, visible: bool) -> None:
        self.query_one("#seasons-loader", LoadingIndicator).styles.display = (
            "block" if visible else "none"
        )
        self.query_one("#season-table", DataTable).styles.display = (
            "none" if visible else "block"
        )

    def _load_seasons(self) -> None:
        try:
            scraper = self.provider.new_series_scraper(self.entry)
            seasons = self.provider.seasons(scraper)
        except Exception as exc:
            self.app.call_from_thread(
                self._set_status, f"[red]Errore caricamento stagioni: {exc}"
            )
            self.app.call_from_thread(self._show_loader, False)
            return

        def apply():
            self._scraper = scraper
            self._seasons = seasons
            table = self.query_one("#season-table", DataTable)
            for season in seasons:
                table.add_row(
                    " ",
                    str(getattr(season, "number", "") or ""),
                    str(getattr(season, "name", "") or ""),
                )
            self._set_status(
                f"[green]{len(seasons)} stagion/i. Invio per selezionare."
            )
            self._show_loader(False)

        self.app.call_from_thread(apply)

    def _set_status(self, text: str) -> None:
        self.query_one("#seasons-status", Static).update(text)

    def _toggle(self, row_index: int) -> None:
        table = self.query_one("#season-table", DataTable)
        if row_index in self._selected:
            self._selected.discard(row_index)
            table.update_cell(RowKey(row_index), "sel", " ")
        else:
            self._selected.add(row_index)
            table.update_cell(RowKey(row_index), "sel", "✓")

    def _apply_ranges(self, text: str) -> None:
        numbers = parse_ranges(text, max_count=len(self._seasons))
        for n in numbers:
            self._selected.add(n - 1)
        table = self.query_one("#season-table", DataTable)
        table.clear()
        for i, season in enumerate(self._seasons):
            table.add_row(
                "✓" if i in self._selected else " ",
                str(getattr(season, "number", "") or ""),
                str(getattr(season, "name", "") or ""),
            )
        self._set_status(f"[green]{len(self._selected)} stagion/i selezionate.")

    @on(DataTable.RowSelected, "#season-table")
    def _on_toggle(self, event: DataTable.RowSelected) -> None:
        try:
            index = int(str(event.row_key.value))
        except (ValueError, TypeError):
            return
        self._toggle(index)

    @on(Input.Submitted, "#season-range")
    def _on_range(self, event: Input.Submitted) -> None:
        self._apply_ranges(event.value)

    @on(Button.Pressed, "#select-all")
    def _select_all(self) -> None:
        self._apply_ranges("*")

    @on(Button.Pressed, "#select-none")
    def _select_none(self) -> None:
        self._selected.clear()
        table = self.query_one("#season-table", DataTable)
        table.clear()
        for season in self._seasons:
            table.add_row(
                " ",
                str(getattr(season, "number", "") or ""),
                str(getattr(season, "name", "") or ""),
            )

    @on(Button.Pressed, "#confirm-btn")
    def _confirm(self) -> None:
        if self._scraper is None:
            return
        if not self._selected:
            try:
                self._selected = set(range(len(self._seasons)))
            except Exception:
                pass
        season_numbers = [int(getattr(self._seasons[i], "number", i + 1)) for i in sorted(self._selected)]
        batch = SeasonBatch(
            provider=self.provider,
            entry=self.entry,
            scraper=self._scraper,
            seasons=season_numbers,
            mode=self.mode,
        )
        first = batch.first()
        if first is not None:
            self.app.push_screen(EpisodesScreen(self.provider, self.entry, batch, first))

    @on(Button.Pressed, "#back-btn")
    def _back(self) -> None:
        self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()