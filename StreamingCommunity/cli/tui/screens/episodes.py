# Episode selection for one season; confirm enqueues the selected episodes.
#
# Mirrors the seasons screen (and search/detail): range input on top, episode
# table on the left, live preview card with confirm/back on the right.

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
from ..formatting import preview_card
from ..providers.base import SeriesFlowProvider
from ..widgets import Header, SelectableTable
from .queue import QueueScreen

INITIAL_PREVIEW = (
    "[dim]Sposta il cursore su un episodio per vederne i dettagli; "
    "imposta un intervallo oppure seleziona con Invio.[/]"
)


class EpisodesScreen(Screen):
    BINDINGS = [("escape", "back", "Indietro")]

    COLUMNS = ("N", "Nome")

    def __init__(
        self,
        provider: SeriesFlowProvider,
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
        self._highlighted: int | None = None
        self._table: SelectableTable | None = None
        # Deferred batch transition, set when a queue finishes and consumed by
        # ``on_screen_resume`` once the queue has actually been popped.
        self._after_queue: str | None = None
        self._pending_season: int | None = None

    @property
    def _selected(self) -> set[int]:
        return self._table.selected if self._table is not None else set()

    def compose(self) -> ComposeResult:
        name = getattr(self.entry, "name", "") or "Sconosciuto"
        yield Header()
        with Vertical(classes="flow-root"):
            yield Label(
                f"[bold #cba6f7]{name}[/] · [#89dceb]S{self.season}[/] · Episodi",
                id="episodes-title",
            )
            with Horizontal(id="episodes-inputs-bar"):
                yield Input(
                    placeholder="Range episodi es. 1,3-5,*",
                    id="episode-range",
                )
                yield Button("Seleziona tutto", id="select-all")
                yield Button("Deseleziona", id="select-none")
            yield Static("", id="episodes-status")
            with Horizontal(id="episodes-split", classes="select-split"):
                with Container(id="table-box"):
                    yield SelectableTable(self.COLUMNS, id="episodes-table")
                    yield LoadingIndicator(id="episodes-loader")
                with Vertical(id="episode-preview-container", classes="select-card"):
                    with Vertical(id="episode-preview-box", classes="select-card-box"):
                        yield Static(INITIAL_PREVIEW, id="episode-preview")
                    with Horizontal(id="episodes-actions", classes="select-actions"):
                        yield Button("Conferma", variant="primary", id="confirm-btn")
                        yield Button("Indietro", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        self._table = self.query_one("#episodes-table", SelectableTable)
        self._table.ensure_columns()
        self._start_season(self.season)

    def _update_title(self) -> None:
        name = getattr(self.entry, "name", "") or "Sconosciuto"
        self.query_one("#episodes-title", Label).update(
            f"[bold #cba6f7]{name}[/] · [#89dceb]S{self.season}[/] · Episodi"
        )

    # ── preview card ──────────────────────────────────────────────────────
    def _set_preview(self, text: str) -> None:
        self.query_one("#episode-preview", Static).update(text)

    def _render_preview(self, index: int | None = None) -> str:
        name = getattr(self.entry, "name", "") or "Sconosciuto"
        badges = (
            f"[dim]Stagione:[/] [#89dceb]S{self.season}[/]   "
            f"[dim]Modalità:[/] [#89dceb]{self.batch.mode}[/]   "
            f"[dim]Episodi:[/] [#89dceb]{len(self._episodes)}[/]"
        )
        details: list[tuple[str, str]] = []
        if index is not None and 0 <= index < len(self._episodes):
            obj = self._episodes[index]
            number = getattr(obj, "number", index + 1)
            details = [
                ("Numero", str(number)),
                ("Nome", str(getattr(obj, "name", "") or "")),
            ]
            try:
                vid = getattr(obj, "video_id", "")
            except Exception:
                vid = ""
            if vid:
                details.append(("Video ID", str(vid)))
        footer = (
            f"[dim]Selezionati:[/] [#a6e3a1]{len(self._selected)}/"
            f"{len(self._episodes)}[/]"
        )
        if index is None and not self._episodes:
            return INITIAL_PREVIEW
        return preview_card(name, badges, details, footer)

    @on(DataTable.RowHighlighted, "#episodes-table")
    def _on_highlighted(self, event: DataTable.RowHighlighted) -> None:
        try:
            index = int(str(event.row_key.value))
        except (ValueError, TypeError):
            return
        self._highlighted = index
        self._set_preview(self._render_preview(index))

    @on(SelectableTable.SelectionChanged, "#episodes-table")
    def _on_selection(self, event: SelectableTable.SelectionChanged) -> None:
        total = event.table.count
        self._set_status(
            f"[#a6e3a1]{len(event.selected)}/{total} episodi selezionati. "
            "Invio per selezionare."
        )
        self._set_preview(self._render_preview(self._highlighted))

    # ── data loading ──────────────────────────────────────────────────────
    def _start_season(self, season: int) -> None:
        """Load (or reload) the episode list for ``season`` on this screen.

        A multi-season batch reuses this same screen for the next season rather
        than pushing a fresh one from the queue's completion callback, which
        raced Textual's teardown. Only one stack action (the queue pop) is ever
        performed from that callback.
        """
        from functools import partial

        self.season = season
        self._episodes = []
        self._highlighted = None
        if self._table is not None:
            self._table.set_rows([])
        self._update_title()
        self._set_preview(INITIAL_PREVIEW)
        self._show_loader(True)
        self.run_worker(
            partial(self._load_episodes), group="episodes", exclusive=True, thread=True
        )

    def _show_loader(self, visible: bool) -> None:
        self.query_one("#episodes-loader", LoadingIndicator).styles.display = (
            "block" if visible else "none"
        )
        self.query_one("#episodes-table", SelectableTable).styles.display = (
            "none" if visible else "block"
        )

    def _set_status(self, text: str) -> None:
        self.query_one("#episodes-status", Static).update(text)

    def _load_episodes(self) -> None:
        try:
            episodes = self.provider.episodes(self.batch.scraper, self.season)
        except Exception as exc:
            self.app.call_from_thread(
                self._set_status, f"[#f38ba8]Errore caricamento episodi: {exc}"
            )
            self.app.call_from_thread(self._show_loader, False)
            return

        def apply():
            self._episodes = episodes
            if self._table is not None:
                self._table.set_rows(
                    (
                        str(getattr(ep, "number", i + 1)),
                        str(getattr(ep, "name", "") or ""),
                    )
                    for i, ep in enumerate(episodes)
                )
            self._show_loader(False)
            self._highlighted = 0
            if self._table is not None and self._table.count:
                self._table.move_cursor(row=0)
            self._set_preview(self._render_preview(0))

        self.app.call_from_thread(apply)

    # ── selection helpers ─────────────────────────────────────────────────
    @on(DataTable.RowSelected, "#episodes-table")
    def _on_toggle(self, event: DataTable.RowSelected) -> None:
        try:
            index = int(str(event.row_key.value))
        except (ValueError, TypeError):
            return
        if self._table is not None:
            self._table.toggle(index)

    @on(Input.Submitted, "#episode-range")
    def _on_range(self, event: Input.Submitted) -> None:
        if self._table is not None:
            self._table.apply_range(event.value)

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
        if not self._episodes:
            return
        selected = self._selected
        if not selected:
            selected = set(range(len(self._episodes)))

        name = getattr(self.entry, "name", "") or "Sconosciuto"
        mode = self.batch.mode
        items = []
        for idx in sorted(selected):
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
        # QueueScreen finished. Only pop the queue here; the revealed screen
        # resumes via ``on_screen_resume``, which advances the batch by exactly
        # one step. Popping several screens from a single completion callback
        # raced Textual's teardown and could hang the whole flow.
        if not self.is_mounted:
            return
        next_season = self.batch.next_after(self.season)
        self._pending_season = next_season
        self._after_queue = "advance" if next_season is not None else "close"
        try:
            self.app.pop_screen()
        except Exception:
            pass

    def on_screen_resume(self) -> None:
        action = self._after_queue
        self._after_queue = None
        if action is None or not self.is_mounted:
            return
        if action == "advance":
            self._start_season(self._pending_season)
            self._pending_season = None
        else:
            # batch finished: drop this episodes screen, back on seasons
            try:
                self.app.pop_screen()
            except Exception:
                pass

    @on(Button.Pressed, "#back-btn")
    def _back(self) -> None:
        self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()