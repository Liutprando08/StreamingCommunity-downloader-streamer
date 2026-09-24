# Episode selection for one season; confirm enqueues the selected episodes.

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
from .queue import QueueScreen


class EpisodesScreen(Screen):
    BINDINGS = [("escape", "back", "Indietro")]

    def __init__(
        self,
        provider: ServiceProvider,
        entry,
        batch: SeasonBatch,
        season: int,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.provider = provider
        self.entry = entry
        self.batch = batch
        self.season = season
        self._episodes = []
        self._selected: set[int] = set()

    def compose(self) -> ComposeResult:
        name = getattr(self.entry, "name", "") or "Sconosciuto"
        yield Header()
        with Vertical(classes="flow-root"):
            yield Label(
                f"[bold magenta]{name}[/] · [cyan]S{self.season}[/] · Episodi",
                id="episodes-title",
            )
            with Container(id="table-box"):
                yield DataTable(id="episodes-table")
                yield LoadingIndicator(id="episodes-loader")
            with Horizontal(id="episodes-actions"):
                yield Input(
                    placeholder="Range episodi es. 1,3-5,*",
                    id="episode-range",
                )
                yield Button("Seleziona tutto", id="select-all")
                yield Button("Deseleziona", id="select-none")
                yield Button("Conferma", variant="primary", id="confirm-btn")
                yield Button("Indietro", id="back-btn")
            yield Static("", id="episodes-status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#episodes-table", DataTable)
        table.add_column("Sel", key="sel")
        table.add_column("N", key="num")
        table.add_column("Nome", key="name")
        table.cursor_type = "row"
        self._show_loader(True)
        from functools import partial
        self.run_worker(partial(self._load_episodes), group="episodes", exclusive=True, thread=True)

    def _show_loader(self, visible: bool) -> None:
        self.query_one("#episodes-loader", LoadingIndicator).styles.display = (
            "block" if visible else "none"
        )
        self.query_one("#episodes-table", DataTable).styles.display = (
            "none" if visible else "block"
        )

    def _set_status(self, text: str) -> None:
        self.query_one("#episodes-status", Static).update(text)

    def _load_episodes(self) -> None:
        try:
            episodes = self.provider.episodes(self.batch.scraper, self.season)
        except Exception as exc:
            self.app.call_from_thread(
                self._set_status, f"[red]Errore caricamento episodi: {exc}"
            )
            self.app.call_from_thread(self._show_loader, False)
            return

        def apply():
            self._episodes = episodes
            table = self.query_one("#episodes-table", DataTable)
            for i, ep in enumerate(episodes):
                num = getattr(ep, "number", i + 1)
                name = getattr(ep, "name", "") or ""
                table.add_row(" ", str(num), str(name))
            self._set_status(
                f"[green]{len(episodes)} episodi. Invio per selezionare."
            )
            self._show_loader(False)

        self.app.call_from_thread(apply)

    def _fill_table(self) -> None:
        table = self.query_one("#episodes-table", DataTable)
        table.clear()
        for i, ep in enumerate(self._episodes):
            num = getattr(ep, "number", i + 1)
            name = getattr(ep, "name", "") or ""
            table.add_row(
                "✓" if i in self._selected else " ",
                str(num),
                str(name),
            )

    @on(DataTable.RowSelected, "#episodes-table")
    def _on_toggle(self, event: DataTable.RowSelected) -> None:
        try:
            index = int(str(event.row_key.value))
        except (ValueError, TypeError):
            return
        table = self.query_one("#episodes-table", DataTable)
        if index in self._selected:
            self._selected.discard(index)
            table.update_cell(RowKey(index), "sel", " ")
        else:
            self._selected.add(index)
            table.update_cell(RowKey(index), "sel", "✓")

    @on(Input.Submitted, "#episode-range")
    def _on_range(self, event: Input.Submitted) -> None:
        for n in parse_ranges(event.value, max_count=len(self._episodes)):
            self._selected.add(n - 1)
        self._fill_table()
        self._set_status(f"[green]{len(self._selected)} episodi selezionati.")

    @on(Button.Pressed, "#select-all")
    def _select_all(self) -> None:
        self._selected = set(range(len(self._episodes)))
        self._fill_table()
        self._set_status(f"[green]{len(self._selected)} episodi selezionati.")

    @on(Button.Pressed, "#select-none")
    def _select_none(self) -> None:
        self._selected.clear()
        self._fill_table()

    @on(Button.Pressed, "#confirm-btn")
    def _confirm(self) -> None:
        if not self._episodes:
            return
        if not self._selected:
            self._selected = set(range(len(self._episodes)))

        name = getattr(self.entry, "name", "") or "Sconosciuto"
        mode = self.batch.mode
        items = []
        for idx in sorted(self._selected):
            ep_num = idx + 1
            obj = self._episodes[idx]
            ep_title = getattr(obj, "name", "") or ""
            items.append(
                {
                    "kind": "episode",
                    "label": f"{name} · S{self.season:02d}E{ep_num:02d} · {ep_title}",
                    "mode": mode,
                    "obj_episode": obj,
                    "season": self.season,
                    "episode": ep_num,
                    "scraper": self.batch.scraper,
                }
            )
        title = f"{mode.capitalize()} · {name} · S{self.season}"
        self.app.push_screen(
            QueueScreen(
                self.provider,
                items,
                title=title,
                on_complete=self._on_queue_done,
            )
        )

    def _on_queue_done(self) -> None:
        if not self.is_mounted:
            return
        queue_popped = True
        try:
            self.app.pop_screen()  # queue
        except Exception:
            queue_popped = False
        nxt = self.batch.next_after(self.season)
        if nxt is not None:
            # replace this episodes screen with the next season's screen
            try:
                self.app.pop_screen()
            except Exception:
                pass
            self.app.push_screen(
                EpisodesScreen(self.provider, self.entry, self.batch, nxt)
            )
        elif queue_popped:
            # close this episodes screen, back on the seasons screen
            try:
                self.app.pop_screen()
            except Exception:
                pass

    @on(Button.Pressed, "#back-btn")
    def _back(self) -> None:
        self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()