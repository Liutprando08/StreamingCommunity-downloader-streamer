# Movie detail: lets the user choose download or stream before enqueuing.

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Label

from ..providers.base import ServiceProvider
from ..widgets import Header
from .queue import QueueScreen
from .seasons import SeasonsScreen


class DetailScreen(Screen):
    BINDINGS = [("escape", "back", "Indietro")]

    def __init__(self, provider: ServiceProvider, entry, is_series: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.provider = provider
        self.entry = entry
        self.is_series = is_series

    def compose(self) -> ComposeResult:
        yield Header()
        can_stream = bool(getattr(self.provider, "supports_streaming", True))
        with Vertical(classes="flow-root"):
            name = getattr(self.entry, "name", "") or "Sconosciuto"
            year = getattr(self.entry, "year", "") or ""
            imdb = (
                getattr(self.entry, "imdb_id", "")
                or getattr(self.entry, "tmdb_id", "")
                or ""
            )
            yield Label(f"[bold magenta]{name}[/]", id="entry-title")
            yield Label(f"[dim]{year} · ID {imdb}[/]", id="entry-meta")
            with Horizontal(id="entry-actions"):
                yield Button("Scarica", variant="primary", id="download-btn")
                if can_stream:
                    yield Button("Streaming", variant="success", id="stream-btn")
                yield Button("Indietro", id="back-btn")
        yield Footer()

    @on(Button.Pressed, "#download-btn")
    def _download(self) -> None:
        self._start("download")

    @on(Button.Pressed, "#stream-btn")
    def _stream(self) -> None:
        self._start("stream")

    @on(Button.Pressed, "#back-btn")
    def _back(self) -> None:
        self.app.pop_screen()

    def _start(self, mode: str) -> None:
        name = getattr(self.entry, "name", "") or "Sconosciuto"

        # Providers without season metadata (torrent) treat the picked entry as
        # one indivisible download and skip the seasons/episodes screens.
        if self.is_series and getattr(self.provider, "supports_seasons", True):
            self.app.push_screen(SeasonsScreen(self.provider, self.entry, mode=mode))
            return

        items = [
            {
                "kind": "film",
                "label": f"{name} ({mode})",
                "mode": mode,
                "entry": self.entry,
            }
        ]
        title = f"{mode.capitalize()} · {name}"
        self.app.push_screen(QueueScreen(self.provider, items, title=title))

    def action_back(self) -> None:
        self.app.pop_screen()