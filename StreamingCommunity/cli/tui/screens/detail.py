# Movie detail: shows the selected title's metadata on the left and the
# download/stream choices on the right, in the same split-card layout as the
# search screen.

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Button, Footer, Static

from ..formatting import detail_lines, entry_info, escape_markup
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

    # ── layout ────────────────────────────────────────────────────────────
    def compose(self) -> ComposeResult:
        yield Header()
        can_stream = bool(getattr(self.provider, "supports_streaming", True))
        with Vertical(classes="flow-root"):
            yield Static("[bold #89dceb]Dettaglio titolo[/]", id="detail-heading")
            with Horizontal(id="detail-split"):
                with Vertical(id="info-box"):
                    yield Static("", id="entry-title")
                    yield Static("", id="entry-badges")
                    yield Static("", id="entry-desc")
                    yield Static("", id="entry-details")
                with Vertical(id="actions-box"):
                    yield Static("[bold #89dceb]Azioni[/]", id="actions-title")
                    yield Button("Scarica", variant="primary", id="download-btn")
                    if can_stream:
                        yield Button("Streaming", variant="success", id="stream-btn")
                    yield Button("Indietro", id="back-btn")
                    yield Static("", id="actions-hint")
        yield Footer()

    def on_mount(self) -> None:
        self._render_info()
        self._load_full_description()

    # ── full synopsis (the API only returns a truncated plot) ─────────────
    @work(thread=True, exclusive=True, group="description")
    def _load_full_description(self) -> None:
        fetch = getattr(self.provider, "entry_description", None)
        if not callable(fetch):
            return
        try:
            full = fetch(self.entry)
        except Exception:
            return
        if full:
            self.app.call_from_thread(self._apply_full_description, full)

    def _apply_full_description(self, text: str) -> None:
        try:
            widget = self.query_one("#entry-desc", Static)
        except NoMatches:
            return
        widget.display = True
        widget.update(f"[italic]{escape_markup(text)}[/]")

    def _render_info(self) -> None:
        entry = self.entry
        name = (
            getattr(entry, "name", "")
            or getattr(entry, "title", "")
            or "Sconosciuto"
        )
        icon, kind = ("📺", "Serie") if self.is_series else ("🎬", "Film")
        provider_name = getattr(self.provider, "name", "")
        language = getattr(entry, "provider_language", "") or ""

        self.query_one("#entry-title", Static).update(f"[bold #cdd6f4]{name}[/]")

        badges = [f"{icon} [bold #a6e3a1]{kind}[/]"]
        if provider_name:
            badges.append(f"[dim]Fonte:[/] [#89dceb]{provider_name}[/]")
        if language:
            badges.append(f"[dim]Lingua:[/] [#89dceb]{language}[/]")
        self.query_one("#entry-badges", Static).update("   ·   ".join(badges))

        # Synopsis, when the provider's entry carries one.
        description = str(
            getattr(entry, "desc", "")
            or getattr(entry, "description", "")
            or getattr(entry, "overview", "")
            or ""
        ).strip()
        desc_widget = self.query_one("#entry-desc", Static)
        if description:
            desc_widget.update(f"[italic]{escape_markup(description)}[/]")
        else:
            desc_widget.display = False

        # Every meaningful field the entry carries: the provider's declared
        # columns first, then any other public attribute (rating, slug, URL…).
        try:
            columns = self.provider.result_columns()
        except Exception:
            columns = ()
        details = detail_lines(
            entry_info(
                entry,
                columns=columns,
                # Already shown as the title / synopsis / badges above.
                exclude={
                    "name",
                    "title",
                    "desc",
                    "description",
                    "overview",
                    "provider_language",
                },
            )
        )
        details_widget = self.query_one("#entry-details", Static)
        if details:
            details_widget.update(
                "[bold #89dceb]Informazioni[/]\n" + "\n".join(details)
            )
        else:
            details_widget.display = False

        hint = (
            "Scegli come procedere con gli episodi."
            if self.is_series
            else "Verrà scaricato in un'unica soluzione."
        )
        self.query_one("#actions-hint", Static).update(f"[dim]{hint}[/]")

    # ── actions ───────────────────────────────────────────────────────────
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
