# Site health screen: checks every configured domain in a background worker.
#
# The probe itself lives in ``utils.site_health``; this screen only renders
# results. Checks run off the UI thread so a slow/dead domain cannot freeze the
# TUI, and rows are appended as each site answers.

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import ClassVar

from rich.markup import escape
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Label, Static

from StreamingCommunity.utils.site_health import (
    UNKNOWN,
    UNREACHABLE,
    WORKING,
    SiteStatus,
    iter_site_checks,
    status_color,
    status_text,
    summary_counts,
)

from ..widgets import Header

COLUMNS = ("Sito", "Stato", "HTTP", "Latenza", "URL / nota")


class SitesScreen(Screen):
    """Reachability report for every site in the registry."""

    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("escape", "back", "Indietro"),
        ("r", "refresh", "Ricontrolla"),
    ]

    def __init__(
        self,
        checker: Callable[[], Iterable[SiteStatus]] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._checker = checker or iter_site_checks
        self._checking = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="flow-root"):
            yield Label("[bold #89dceb]Stato dei siti[/]", id="sites-title")
            yield Static("", id="sites-summary")
            with Container(id="table-box"):
                yield DataTable(id="sites-table")
            with Horizontal(id="sites-actions"):
                yield Button("Ricontrolla", variant="primary", id="sites-refresh")
                yield Button("Indietro", id="sites-back")
            yield Static("", id="sites-status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#sites-table", DataTable)
        table.add_columns(*COLUMNS)
        table.cursor_type = "row"
        self._start_check()

    # ── actions ───────────────────────────────────────────────────────────
    def action_back(self) -> None:
        self.app.pop_screen()

    def action_refresh(self) -> None:
        self._start_check()

    @on(Button.Pressed, "#sites-refresh")
    def _on_refresh(self) -> None:
        self._start_check()

    @on(Button.Pressed, "#sites-back")
    def _on_back(self) -> None:
        self.app.pop_screen()

    # ── checking ──────────────────────────────────────────────────────────
    def _start_check(self) -> None:
        if self._checking:
            return
        self._checking = True
        self.query_one("#sites-table", DataTable).clear()
        self.query_one("#sites-refresh", Button).disabled = True
        self._set_summary("[yellow]Controllo in corso…[/]")
        self._set_status("[dim]Le richieste partono in parallelo.[/]")
        self.run_worker(
            self._collect,
            thread=True,
            exclusive=True,
            group="site-check",
        )

    def _collect(self) -> None:
        results: list[SiteStatus] = []
        try:
            for result in self._checker():
                results.append(result)
                self._post(self._add_row, result)
        except Exception as exc:  # noqa: BLE001 - surface worker errors in the UI
            self._post(self._finish_error, exc)
            return
        self._post(self._finish, results)

    def _post(self, callback, *args) -> None:
        """Schedule a UI update from the worker thread, if the app still runs."""
        try:
            self.app.call_from_thread(callback, *args)
        except RuntimeError:
            # The screen/app was closed while the worker was still running.
            return

    # ── rendering ─────────────────────────────────────────────────────────
    def _add_row(self, result: SiteStatus) -> None:
        if not self.is_mounted:
            return
        label = status_text(result.status, italian=True)
        color = status_color(result.status)
        http = str(result.http_status) if result.http_status is not None else "-"
        latency = f"{result.latency_ms} ms" if result.latency_ms is not None else "-"
        target = escape(result.url) if result.url else "-"
        if result.detail:
            target = f"{target}\n[dim]{escape(result.detail)}[/]"
        self.query_one("#sites-table", DataTable).add_row(
            result.name,
            f"[{color}]{label}[/]",
            http,
            latency,
            target,
            key=result.name,
        )

    def _finish(self, results: list[SiteStatus]) -> None:
        if not self.is_mounted:
            return
        self._checking = False
        self.query_one("#sites-refresh", Button).disabled = False
        counts = summary_counts(results)
        self._set_summary(
            f"[green]Funzionanti: {counts[WORKING]}[/] · "
            f"[red]Non raggiungibili: {counts[UNREACHABLE]}[/] · "
            f"[yellow]Sconosciuti: {counts[UNKNOWN]}[/]"
        )
        if counts[UNREACHABLE]:
            self._set_status(
                "[yellow]Alcuni siti non rispondono. Controlla connessione/proxy "
                "e riprova più tardi.[/]"
            )
        else:
            self._set_status("[green]Tutti i siti controllati hanno risposto.[/]")

    def _finish_error(self, exc: BaseException) -> None:
        if not self.is_mounted:
            return
        self._checking = False
        self.query_one("#sites-refresh", Button).disabled = False
        self._set_summary("[red]Controllo non riuscito.[/]")
        self._set_status(f"[red]{escape(str(exc))}[/]")

    def _set_summary(self, text: str) -> None:
        self.query_one("#sites-summary", Static).update(text)

    def _set_status(self, text: str) -> None:
        self.query_one("#sites-status", Static).update(text)
