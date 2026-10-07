# Music flow: pick a search mode, run the query, then drill down
# artist -> album -> tracks before enqueuing the selected tracks.
#
# All four levels (search / results / albums / tracks) share one screen so the
# breadcrumb and "back" behaviour stay in a single place.

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
    Select,
    Static,
)
from textual.widgets.data_table import RowKey

from ..parse import parse_ranges
from ..providers.base import MusicProvider
from ..widgets import Header
from .queue import QueueScreen

LEVEL_SEARCH = "search"
LEVEL_RESULTS = "results"
LEVEL_ALBUMS = "albums"
LEVEL_TRACKS = "tracks"


class MusicScreen(Screen):
    BINDINGS = [("escape", "back", "Indietro")]

    # Textual's MessagePump/DOM already owns these names; assigning to them
    # detaches the widget from the tree and silently stops message bubbling.
    RESERVED_ATTRS = ("_parent", "_context")

    def __init__(self, provider: MusicProvider, **kwargs):
        super().__init__(**kwargs)
        for reserved in self.RESERVED_ATTRS:
            if reserved in vars(self):
                raise AttributeError(
                    f"{reserved} is reserved by Textual; pick another name."
                )
        self.provider = provider
        self._level = LEVEL_SEARCH
        self._mode = ""
        self._entries: list = []
        # Breadcrumb of (level, entries, context) restored by "back".
        self._history: list[tuple[str, list, object]] = []
        self._parent_entry = None
        self._selected: set[int] = set()

    # ── layout ────────────────────────────────────────────────────────────
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="flow-root"):
            yield Label("", id="music-title")
            yield Select(
                [(mode, mode) for mode in self.provider.search_modes()],
                id="music-mode",
                allow_blank=False,
            )
            yield Input(
                placeholder="Insert the title (ex. Nirvana)", id="music-query"
            )
            with Container(id="table-box"):
                yield DataTable(id="music-table")
                yield LoadingIndicator(id="music-loader")
            with Horizontal(id="music-actions"):
                yield Input(placeholder="Range tracce es. 1,3-5,*", id="track-range")
                yield Button("Seleziona tutto", id="select-all")
                yield Button("Deseleziona", id="select-none")
                yield Button("Conferma", variant="primary", id="confirm-btn")
                yield Button("Indietro", id="back-btn")
            yield Static("", id="music-status")
        yield Footer()

    def on_mount(self) -> None:
        modes = self.provider.search_modes()
        if modes:
            self._mode = modes[0]
            self.query_one("#music-mode", Select).value = modes[0]

        self.query_one("#music-table", DataTable).cursor_type = "row"
        self._show_loader(False)
        self._apply_level()

    # ── level rendering ───────────────────────────────────────────────────
    def _apply_level(self) -> None:
        """Show only the widgets that make sense for the current level."""
        at_search = self._level == LEVEL_SEARCH
        table_rows = not at_search

        self.query_one("#music-mode", Select).display = at_search
        self.query_one("#music-query", Input).display = at_search
        self.query_one("#music-actions", Horizontal).display = table_rows
        self.query_one("#table-box", Container).display = table_rows

        if not at_search:
            # Only focus once the box is visible: focusing a display:none
            # widget is silently dropped by Textual.
            self.query_one("#music-table", DataTable).focus()

        if at_search:
            self._set_title(f"Music · {self.provider.name}")
            self._set_status("[dim]Scegli una modalità e premi Invio.")
            return

        if self._level == LEVEL_TRACKS:
            self._set_title(
                f"{self.provider.name} · {getattr(self._parent_entry, 'name', '')} · Tracce"
            )
            self._set_status(
                f"[green]{len(self._entries)} tracce. Invio per selezionare."
            )
        elif self._level == LEVEL_ALBUMS:
            self._set_title(
                f"{self.provider.name} · {getattr(self._parent_entry, 'name', '')} · Album"
            )
            self._set_status(
                f"[green]{len(self._entries)} album. Invio per aprire le tracce."
            )
        else:
            self._set_title(f"Music · {self.provider.name} · {self._mode}")
            self._set_status(
                f"[green]{len(self._entries)} risultato/i. Invio per aprire."
            )

    def _fill_table(self) -> None:
        table = self.query_one("#music-table", DataTable)
        columns = self.provider.result_columns()
        # columns=True is required: clear() alone keeps explicit column keys,
        # so a second fill would raise DuplicateKey and kill the screen.
        table.clear(columns=True)
        # Sel/N mirror the episodes screen: they drive the range selection.
        table.add_column("Sel", key="sel")
        table.add_column("N", key="num")
        for header, _attr in columns:
            table.add_column(header)
        for i, entry in enumerate(self._entries):
            table.add_row(
                "✓" if i in self._selected else " ",
                str(i + 1),
                *[str(getattr(entry, attr, "") or "") for _, attr in columns],
                key=str(i),
            )
        table.cursor_type = "row"

    def _show_loader(self, visible: bool) -> None:
        self.query_one("#music-loader", LoadingIndicator).styles.display = (
            "block" if visible else "none"
        )
        self.query_one("#music-table", DataTable).styles.display = (
            "none" if visible else "block"
        )

    def _set_title(self, text: str) -> None:
        self.query_one("#music-title", Label).update(f"[bold cyan]{text}[/]")

    def _set_status(self, text: str) -> None:
        self.query_one("#music-status", Static).update(text)

    # ── search ────────────────────────────────────────────────────────────
    @on(Input.Submitted, "#music-query")
    def _on_submit(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if not query:
            return

        select = self.query_one("#music-mode", Select)
        self._mode = str(select.value) if select.value is not None else ""

        self._set_status("[yellow]Ricerca in corso...")
        self._show_loader(True)
        self._history.clear()

        from functools import partial

        self.run_worker(
            partial(self._do_search, query, self._mode),
            group="music-search",
            exclusive=True,
            thread=True,
        )

    def _do_search(self, query: str, mode: str) -> None:
        try:
            results = self.provider.search(query, mode)
        except Exception as exc:
            self.app.call_from_thread(
                self._set_status, f"[red]Errore ricerca: {exc}"
            )
            self.app.call_from_thread(self._show_loader, False)
            return

        def apply():
            self._level = LEVEL_RESULTS
            self._entries = list(results)
            self._parent_entry = None
            self._selected.clear()
            # Restore visibility before filling/focusing: Textual silently
            # drops focus() on a display:none widget.
            self._show_loader(False)
            self._fill_table()
            self._apply_level()
            if not self._entries:
                self._set_status("[yellow]Nessun risultato trovato.")

        self.app.call_from_thread(apply)

    # ── drill-down ────────────────────────────────────────────────────────
    def _push_level(self, level: str, entries: list, context: object) -> None:
        self._history.append((self._level, self._entries, self._parent_entry))
        self._level = level
        self._entries = list(entries)
        self._parent_entry = context
        self._selected.clear()
        self._fill_table()
        self._apply_level()

    @on(DataTable.RowSelected, "#music-table")
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        self._select_row(event.row_key)

    def _select_row(self, row_key: RowKey | str) -> None:
        raw = row_key.value if isinstance(row_key, RowKey) else row_key
        try:
            index = int(str(raw))
        except (ValueError, TypeError):
            return
        if index < 0 or index >= len(self._entries):
            return
        entry = self._entries[index]

        if self._level == LEVEL_TRACKS:
            self._toggle(index)
            return

        # Results and albums both descend through the provider's drilldown:
        # artist -> albums, album -> tracks, song -> None (download directly).
        target = self.provider.drilldown(entry)
        if target is None:
            self._enqueue_tracks([entry], title=str(getattr(entry, "name", "") or ""))
            return

        level, items = target
        if not items:
            self._set_status(
                f"[yellow]Nessun contenuto per {getattr(entry, 'name', '?')}."
            )
            return
        self._push_level(level, items, entry)

    # ── track selection ───────────────────────────────────────────────────
    def _toggle(self, index: int) -> None:
        table = self.query_one("#music-table", DataTable)
        if index in self._selected:
            self._selected.discard(index)
        else:
            self._selected.add(index)
        self._sync_selection()

    def _sync_selection(self) -> None:
        table = self.query_one("#music-table", DataTable)
        for i in range(len(self._entries)):
            marker = "✓" if i in self._selected else " "
            table.update_cell(RowKey(str(i)), "sel", marker)

    @on(Input.Submitted, "#track-range")
    def _on_range(self, event: Input.Submitted) -> None:
        if self._level != LEVEL_TRACKS:
            return
        for n in parse_ranges(event.value, max_count=len(self._entries)):
            self._selected.add(n - 1)
        self._sync_selection()
        self._set_status(f"[green]{len(self._selected)} tracce selezionate.")

    @on(Button.Pressed, "#select-all")
    def _select_all(self) -> None:
        if self._level != LEVEL_TRACKS:
            return
        self._selected = set(range(len(self._entries)))
        self._sync_selection()
        self._set_status(f"[green]{len(self._selected)} tracce selezionate.")

    @on(Button.Pressed, "#select-none")
    def _select_none(self) -> None:
        if self._level != LEVEL_TRACKS:
            return
        self._selected.clear()
        self._sync_selection()
        self._set_status("[green]0 tracce selezionate.")

    @on(Button.Pressed, "#confirm-btn")
    def _confirm(self) -> None:
        if self._level != LEVEL_TRACKS:
            return
        if not self._entries:
            return
        if not self._selected:
            self._selected = set(range(len(self._entries)))

        album = getattr(self._parent_entry, "name", "") or "Album"
        tracks = [self._entries[i] for i in sorted(self._selected)]
        self._enqueue_tracks(tracks, title=album)

    def _enqueue_tracks(self, tracks: list, title: str) -> None:
        items = []
        for track in tracks:
            name = getattr(track, "name", "") or "?"
            artist = getattr(track, "artist", "") or ""
            label = f"{artist} - {name}" if artist else name
            items.append(
                {
                    "kind": "track",
                    "label": label,
                    "mode": "download",
                    "entry": track,
                }
            )
        self.app.push_screen(
            QueueScreen(self.provider, items, title=f"Download · {title}")
        )

    # ── navigation ────────────────────────────────────────────────────────
    def _back(self) -> None:
        if self._level == LEVEL_SEARCH:
            self.app.pop_screen()
            return

        if not self._history:
            self._level = LEVEL_SEARCH
            self._entries = []
            self._parent_entry = None
            self._selected.clear()
            self._fill_table()
            self._apply_level()
            return

        level, entries, context = self._history.pop()
        self._level = level
        self._entries = entries
        self._parent_entry = context
        self._selected.clear()
        self._fill_table()
        self._apply_level()

    @on(Button.Pressed, "#back-btn")
    def _on_back_button(self) -> None:
        self._back()

    def action_back(self) -> None:
        self._back()