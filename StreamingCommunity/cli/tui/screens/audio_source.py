# Italian audio source picker for the torrent flow.
#
# The CLI asks for the StreamingCommunity title on stdin *after* the torrent
# download (``prompt_audio_dub``), which would freeze a TUI worker thread
# forever. Here the source is gathered *before* enqueueing instead: the queue
# worker then downloads the audio and runs the mux non-interactively.
#
# Reuses the same split-card layout as search/seasons (table on the left is not
# needed here, so the whole screen is one card). When ``TORRENT.auto_mux`` is
# true the search runs automatically and the first result is taken, mirroring
# the CLI --no-prompt behaviour.

from __future__ import annotations

from functools import partial
from typing import Any

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

from ..widgets import Header
from .queue import QueueScreen

INITIAL_STATUS = (
    "[dim]Cerca il titolo su StreamingCommunity, poi scegli la voce da cui "
    "prendere l'audio italiano.[/]"
)


class AudioSourceScreen(Screen):
    BINDINGS = [("escape", "back", "Indietro")]

    def __init__(self, provider: Any, entry: Any, mode: str = "download", **kwargs):
        super().__init__(**kwargs)
        self.provider = provider
        self.entry = entry
        self.mode = mode
        self._entries: list[Any] = []
        self._highlighted: int | None = None

    def compose(self) -> ComposeResult:
        target = getattr(self.entry, "name", "") or "Sconosciuto"
        yield Header()
        with Vertical(classes="flow-root"):
            yield Static(
                f"[bold #89dceb]Audio italiano[/] · [dim]per[/] "
                f"[#cdd6f4]{target}[/]",
                id="audio-title",
            )
            with Horizontal(id="audio-inputs-bar"):
                yield Input(
                    value=target,
                    placeholder="Titolo su StreamingCommunity",
                    id="audio-query",
                )
                yield Button("Cerca", variant="primary", id="audio-search-btn")
            yield Static(INITIAL_STATUS, id="audio-status")
            with Container(id="table-box"):
                yield DataTable(id="audio-results")
                yield LoadingIndicator(id="audio-loader")
            with Horizontal(id="audio-actions"):
                yield Button("Salta audio", id="audio-skip-btn")
                yield Button("Indietro", id="audio-back-btn")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#audio-results", DataTable)
        table.add_columns(*[header for header, _attr in self._columns()])
        table.cursor_type = "row"
        self._show_loader(False)
        self.query_one("#audio-query", Input).focus()

    def _auto_mux(self) -> bool:
        try:
            from StreamingCommunity.torrent.config import TorrentConfig
            from StreamingCommunity.utils import config_manager

            return bool(TorrentConfig(config_manager).auto_mux)
        except Exception:
            return False

    def _columns(self) -> tuple[tuple[str, str], ...]:
        try:
            from ..providers import registry

            sc = registry.get("streamingcommunity")
            if sc is not None:
                return sc.result_columns()
        except Exception:
            pass
        return (("Nome", "name"), ("Tipo", "type"), ("Anno", "year"))

    def _show_loader(self, visible: bool) -> None:
        self.query_one("#audio-loader", LoadingIndicator).styles.display = (
            "block" if visible else "none"
        )
        self.query_one("#audio-results", DataTable).styles.display = (
            "none" if visible else "block"
        )

    def _set_status(self, text: str) -> None:
        self.query_one("#audio-status", Static).update(text)

    @on(Input.Submitted, "#audio-query")
    @on(Button.Pressed, "#audio-search-btn")
    def _on_submit(self, event) -> None:
        query = self.query_one("#audio-query", Input).value.strip()
        if not query:
            self._set_status("[#f9e2af]Inserisci un titolo da cercare.")
            return
        self._run_search(query)

    def _run_search(self, query: str) -> None:
        self._set_status("[#f9e2af]Ricerca su StreamingCommunity...")
        self._show_loader(True)
        self.run_worker(
            partial(self._do_search, query),
            group="audio-search",
            exclusive=True,
            thread=True,
        )

    def _do_search(self, query: str) -> None:
        try:
            results = self.provider.search_audio_sources(query)
        except Exception as exc:
            self.app.call_from_thread(self._set_status, f"[#f38ba8]Errore: {exc}")
            self.app.call_from_thread(self._show_loader, False)
            return

        def apply() -> None:
            self._entries = list(results)
            columns = self._columns()
            table = self.query_one("#audio-results", DataTable)
            table.clear()
            for idx, entry in enumerate(self._entries):
                table.add_row(
                    *[str(getattr(entry, attr, "") or "") for _, attr in columns],
                    key=str(idx),
                )
            self._show_loader(False)
            if not self._entries:
                if self._auto_mux():
                    self._set_status(
                        "[#f9e2af]Nessun risultato con auto_mux, procedo senza audio ITA."
                    )
                    # Proceed without dubbing
                    self._enqueue(None)
                    return
                self._set_status(
                    "[#f9e2af]Nessun risultato. Modifica la ricerca o salta l'audio."
                )
                return
            table.move_cursor(row=0)
            self._highlighted = 0
            self._set_status(
                f"[#a6e3a1]{len(self._entries)} risultato/i. Invio per usare questo audio."
            )

        self.app.call_from_thread(apply)

    @on(DataTable.RowHighlighted, "#audio-results")
    def _on_highlighted(self, event: DataTable.RowHighlighted) -> None:
        try:
            self._highlighted = int(str(event.row_key.value))
        except (ValueError, TypeError):
            pass

    @on(DataTable.RowSelected, "#audio-results")
    def _on_selected(self, event: DataTable.RowSelected) -> None:
        try:
            index = int(str(event.row_key.value))
        except (ValueError, TypeError):
            return
        self._pick(index)

    def _pick(self, index: int) -> None:
        if index < 0 or index >= len(self._entries):
            return
        self._enqueue(self._entries[index])

    @on(Button.Pressed, "#audio-skip-btn")
    def _skip(self) -> None:
        self._enqueue(None)

    @on(Button.Pressed, "#audio-back-btn")
    def _back(self) -> None:
        self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()

    def _enqueue(self, source: Any) -> None:
        name = getattr(self.entry, "name", "") or "Sconosciuto"
        label = f"{name} ({self.mode})"
        item: dict[str, Any] = {
            "kind": "film",
            "label": label,
            "mode": self.mode,
            "entry": self.entry,
        }
        if source is not None:
            item["dub_entry"] = source
            item["label"] = f"{label} + audio ITA"
        title = f"{self.mode.capitalize()} · {name}"
        self.app.push_screen(QueueScreen(self.provider, [item], title=title))
