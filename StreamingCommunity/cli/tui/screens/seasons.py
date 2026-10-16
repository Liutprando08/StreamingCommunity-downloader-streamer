# Season selection: multi-select table, then a batch starts walking
# season-by-season through the episodes screen.
#
# Same split-card layout as search/detail: range input on top, table on the
# left and a live "selection" card on the right with the confirm/back actions.

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Input,
    Label,
    LoadingIndicator,
    Static,
)

from ..flow import SeasonBatch
from ..formatting import format_number, preview_card
from ..providers.base import ServiceProvider
from ..widgets import Header, SelectableTable
from .episodes import EpisodesScreen

INITIAL_PREVIEW = (
    "[dim]Sposta il cursore su una stagione per vederne i dettagli; "
    "imposta un intervallo oppure seleziona con Invio.[/]"
)


class SeasonsScreen(Screen):
    BINDINGS = [("escape", "back", "Indietro")]

    COLUMNS = ("Stagione", "Nome")

    def __init__(
        self, provider: ServiceProvider, entry, mode: str = "download", **kwargs
    ):
        super().__init__(**kwargs)
        self.provider = provider
        self.entry = entry
        self.mode = mode
        self._scraper = None
        self._seasons = []
        self._highlighted: int | None = None
        self._table: SelectableTable | None = None

    @property
    def _selected(self) -> set[int]:
        return self._table.selected if self._table is not None else set()

    def compose(self) -> ComposeResult:
        name = getattr(self.entry, "name", "") or "Sconosciuto"
        yield Header()
        with Vertical(classes="flow-root"):
            yield Label(
                f"[bold #cba6f7]{name}[/] · [#89dceb]Stagioni[/]",
                id="seasons-title",
            )
            with Horizontal(id="seasons-inputs-bar"):
                yield Input(
                    placeholder="Range stagioni es. 1,3-5,*",
                    id="season-range",
                )
                yield Button("Seleziona tutto", id="select-all")
                yield Button("Deseleziona", id="select-none")
            yield Static("", id="seasons-status")
            with Horizontal(id="seasons-split", classes="select-split"):
                with Container(id="table-box"):
                    yield SelectableTable(self.COLUMNS, id="season-table")
                    yield LoadingIndicator(id="seasons-loader")
                with Vertical(id="season-preview-container", classes="select-card"):
                    with Vertical(id="season-preview-box", classes="select-card-box"):
                        yield Static(INITIAL_PREVIEW, id="season-preview")
                    with Horizontal(id="seasons-actions", classes="select-actions"):
                        yield Button("Conferma", variant="primary", id="confirm-btn")
                        yield Button("Indietro", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        self._table = self.query_one("#season-table", SelectableTable)
        self._table.ensure_columns()
        self._show_loader(True)
        from functools import partial

        self.run_worker(
            partial(self._load_seasons), group="seasons", exclusive=True, thread=True
        )

    def _show_loader(self, visible: bool) -> None:
        self.query_one("#seasons-loader", LoadingIndicator).styles.display = (
            "block" if visible else "none"
        )
        self.query_one("#season-table", SelectableTable).styles.display = (
            "none" if visible else "block"
        )

    def _set_status(self, text: str) -> None:
        self.query_one("#seasons-status", Static).update(text)

    def _set_preview(self, text: str) -> None:
        self.query_one("#season-preview", Static).update(text)

    # ── preview card ──────────────────────────────────────────────────────
    def _render_preview(self, index: int | None = None) -> str:
        name = getattr(self.entry, "name", "") or "Sconosciuto"
        badges = (
            f"[dim]Modalità:[/] [#89dceb]{self.mode}[/]   "
            f"[dim]Stagioni:[/] [#89dceb]{len(self._seasons)}[/]"
        )
        details: list[tuple[str, str]] = []
        if index is not None and 0 <= index < len(self._seasons):
            season = self._seasons[index]
            details = [
                ("Numero", format_number(getattr(season, "number", ""))),
                ("Nome", str(getattr(season, "name", "") or "")),
            ]
            extra = getattr(season, "id", "")
            if extra:
                details.append(("ID", str(extra)))
        footer = (
            f"[dim]Selezionate:[/] [#a6e3a1]{len(self._selected)}/"
            f"{len(self._seasons)}[/]"
        )
        if index is None and not self._seasons:
            return INITIAL_PREVIEW
        return preview_card(name, badges, details, footer)

    @on(DataTable.RowHighlighted, "#season-table")
    def _on_highlighted(self, event: DataTable.RowHighlighted) -> None:
        try:
            index = int(str(event.row_key.value))
        except (ValueError, TypeError):
            return
        self._highlighted = index
        self._set_preview(self._render_preview(index))

    @on(SelectableTable.SelectionChanged, "#season-table")
    def _on_selection(self, event: SelectableTable.SelectionChanged) -> None:
        total = event.table.count
        self._set_status(
            f"[#a6e3a1]{len(event.selected)}/{total} stagion/i selezionate. "
            "Invio per selezionare."
        )
        self._set_preview(self._render_preview(self._highlighted))

    # ── data loading ──────────────────────────────────────────────────────
    def _load_seasons(self) -> None:
        try:
            scraper = self.provider.new_series_scraper(self.entry)
            seasons = self.provider.seasons(scraper)
        except Exception as exc:
            self.app.call_from_thread(
                self._set_status, f"[#f38ba8]Errore caricamento stagioni: {exc}"
            )
            self.app.call_from_thread(self._show_loader, False)
            return

        def apply():
            self._scraper = scraper
            self._seasons = seasons
            if self._table is not None:
                self._table.set_rows(
                    (
                        format_number(getattr(season, "number", "")),
                        str(getattr(season, "name", "") or ""),
                    )
                    for season in seasons
                )
            self._show_loader(False)
            self._highlighted = 0
            if self._table is not None and self._table.count:
                self._table.move_cursor(row=0)
            self._set_preview(self._render_preview(0))

        self.app.call_from_thread(apply)

    # ── selection helpers ─────────────────────────────────────────────────
    def _apply_ranges(self, text: str) -> None:
        if self._table is not None:
            self._table.apply_range(text)

    @on(DataTable.RowSelected, "#season-table")
    def _on_toggle(self, event: DataTable.RowSelected) -> None:
        try:
            index = int(str(event.row_key.value))
        except (ValueError, TypeError):
            return
        if self._table is not None:
            self._table.toggle(index)

    @on(Input.Submitted, "#season-range")
    def _on_range(self, event: Input.Submitted) -> None:
        self._apply_ranges(event.value)

    @on(Button.Pressed, "#select-all")
    def _select_all(self) -> None:
        if self._table is not None:
            self._table.select_all()

    @on(Button.Pressed, "#select-none")
    def _select_none(self) -> None:
        if self._table is not None:
            self._table.select_none()

    @on(Button.Pressed, "#confirm-btn")
    def _confirm(self) -> None:
        if self._scraper is None:
            return
        selected = self._selected
        if not selected:
            selected = set(range(len(self._seasons)))
        season_numbers = [
            int(getattr(self._seasons[i], "number", i + 1)) for i in sorted(selected)
        ]
        batch = SeasonBatch(
            provider=self.provider,
            entry=self.entry,
            scraper=self._scraper,
            seasons=season_numbers,
            mode=self.mode,
        )
        first = batch.first()
        if first is not None:
            self.app.push_screen(
                EpisodesScreen(self.provider, self.entry, batch, first)
            )

    @on(Button.Pressed, "#back-btn")
    def _back(self) -> None:
        self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()