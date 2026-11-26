"""Mobile-first Flet interface for the downloader core."""

# The UI must never crash on a failing site/download: broad catches are
# intentional and surfaced to the user instead of logged.
# ruff: noqa: BLE001, S110

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import flet as ft

from . import core, theme

SECTORS = (
    ("all", "Tutti"),
    ("film", "Film & Serie"),
    ("music", "Musica"),
    ("books", "Libri"),
    ("other", "Altro"),
)


@dataclass
class View:
    kind: str
    title: str
    data: dict[str, Any] = field(default_factory=dict)


def main(page: ft.Page) -> None:
    OsteApp(page).start()


class OsteApp:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.manager = core.DownloadManager()
        self._stack: list[View] = []
        self._tab = 0
        self._sector = "all"
        self._home_query: ft.TextField | None = None
        self._home_sector: ft.Dropdown | None = None
        self._content = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
            controls=[],
        )
        self._body = ft.Container(
            content=self._content,
            expand=True,
            padding=ft.padding.symmetric(horizontal=14, vertical=10),
        )

    # ── page setup ────────────────────────────────────────────────────────
    def start(self) -> None:
        page = self.page
        page.title = "OSTE Mobile"
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor = theme.BG
        page.theme = ft.Theme(color_scheme_seed=theme.PRIMARY)
        page.padding = 0
        try:
            page.window.width = 430
            page.window.height = 900
        except Exception:
            pass

        page.navigation_bar = ft.NavigationBar(
            selected_index=0,
            bgcolor=theme.SURFACE,
            indicator_color=ft.Colors.with_opacity(0.22, theme.PRIMARY),
            destinations=[
                ft.NavigationBarDestination(
                    icon=ft.Icons.HOME_OUTLINED,
                    selected_icon=ft.Icons.HOME,
                    label="Home",
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.DOWNLOAD_OUTLINED,
                    selected_icon=ft.Icons.DOWNLOAD,
                    label="Download",
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.SETTINGS_OUTLINED,
                    selected_icon=ft.Icons.SETTINGS,
                    label="Impostazioni",
                ),
            ],
            on_change=self._on_nav_change,
        )
        page.add(ft.SafeArea(self._body, expand=True))
        self._go_home()
        page.run_task(self._ticker)

    def _on_nav_change(self, event: ft.ControlEvent) -> None:
        try:
            index = int(event.control.selected_index)
        except Exception:
            return
        if index == self._tab:
            return
        if index == 0:
            self._go_home()
        elif index == 1:
            self._go_downloads()
        else:
            self._go_settings()

    def _set_tab(self, index: int) -> None:
        self._tab = index
        if self.page.navigation_bar is not None:
            self.page.navigation_bar.selected_index = index

    def _go_home(self) -> None:
        self._set_tab(0)
        self._stack = [View("home", "OSTE Mobile")]
        self._render()

    def _go_downloads(self) -> None:
        self._set_tab(1)
        self._stack = [View("downloads", "Download")]
        self._render()

    def _go_settings(self) -> None:
        self._set_tab(2)
        self._stack = [View("settings", "Impostazioni")]
        self._render()

    # ── view stack ────────────────────────────────────────────────────────
    def _push(self, view: View) -> None:
        self._stack.append(view)
        self._render()

    def _back(self) -> None:
        if len(self._stack) > 1:
            self._stack.pop()
            self._render()
        elif self._tab != 0:
            self._go_home()

    def _view_is(self, data: dict[str, Any]) -> bool:
        return bool(self._stack) and self._stack[-1].data is data

    def _render(self) -> None:
        if not self._stack:
            return
        view = self._stack[-1]
        builder = getattr(self, f"_build_{view.kind}", None)
        if builder is None:
            controls: list[ft.Control] = [self._error_card(f"Vista sconosciuta: {view.kind}")]
        else:
            try:
                controls = builder(view.data)
            except Exception as exc:
                controls = [self._error_card(f"Errore interfaccia: {exc}")]

        self._content.controls = controls
        leading = None
        if len(self._stack) > 1:
            leading = ft.IconButton(
                icon=ft.Icons.ARROW_BACK,
                icon_color=theme.TEXT,
                on_click=lambda e: self._back(),
            )
        self.page.appbar = ft.AppBar(
            title=ft.Text(
                view.title,
                size=17,
                weight=ft.FontWeight.BOLD,
                color=theme.TEXT,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
            leading=leading,
            bgcolor=theme.SURFACE,
            color=theme.TEXT,
        )
        self.page.update()

    def _post(self, handler: Callable[..., Any], *args: Any) -> None:
        try:
            self.page.run_task(handler, *args)
        except Exception:
            pass

    def _toast(self, message: str, error: bool = False) -> None:
        try:
            self.page.open(
                ft.SnackBar(
                    content=ft.Text(str(message), color=theme.TEXT),
                    bgcolor=theme.RED if error else theme.SURFACE_HI,
                    duration=2800,
                )
            )
        except Exception:
            pass

    # ── shared widgets ────────────────────────────────────────────────────
    @staticmethod
    def _error_card(message: str) -> ft.Container:
        return theme.card(
            ft.Row(
                [
                    ft.Icon(ft.Icons.ERROR_OUTLINE, color=theme.RED, size=20),
                    ft.Text(str(message), color=theme.TEXT, size=13, expand=True),
                ],
                spacing=10,
            ),
            bgcolor=ft.Colors.with_opacity(0.12, theme.RED),
        )

    def _empty(self, text: str, icon: str = "SEARCH") -> ft.Container:
        return theme.card(
            ft.Column(
                [
                    ft.Icon(getattr(ft.Icons, icon, ft.Icons.SEARCH), color=theme.MUTED, size=34),
                    ft.Text(text, color=theme.MUTED, size=13, text_align=ft.TextAlign.CENTER),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            bgcolor=theme.SURFACE,
        )

    def _provider_header(self, provider: Any) -> ft.Container:
        return theme.card(
            ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(core.provider_icon(provider), color=theme.PRIMARY, size=26),
                        width=48,
                        height=48,
                        bgcolor=theme.SURFACE_HI,
                        border_radius=14,
                        alignment=ft.alignment.center,
                    ),
                    ft.Column(
                        [
                            ft.Text(
                                getattr(provider, "name", "Servizio"),
                                size=16,
                                weight=ft.FontWeight.BOLD,
                                color=theme.TEXT,
                            ),
                            theme.muted(core.provider_kind_label(provider)),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
            )
        )

    def _list_card(
        self,
        title: str,
        subtitle: str = "",
        leading: ft.Control | None = None,
        trailing: ft.Control | None = None,
        on_click: Callable[[ft.ControlEvent], None] | None = None,
    ) -> ft.Container:
        return theme.card(
            ft.ListTile(
                title=ft.Text(
                    title,
                    size=14,
                    weight=ft.FontWeight.W_600,
                    color=theme.TEXT,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                subtitle=ft.Text(
                    subtitle,
                    size=11,
                    color=theme.MUTED,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                )
                if subtitle
                else None,
                leading=leading,
                trailing=trailing,
                on_click=on_click,
                content_padding=ft.padding.symmetric(horizontal=2, vertical=0),
                min_height=56,
            ),
            padding=ft.padding.symmetric(horizontal=12, vertical=2),
        )

    def _entry_card(self, provider: Any, entry: Any, trailing=None, on_click=None) -> ft.Container:
        if on_click is None:
            on_click = lambda e: self._open_entry(provider, entry)
        return self._list_card(
            core.entry_name(entry),
            core.entry_subtitle(provider, entry),
            leading=ft.Icon(core.provider_icon(provider), color=theme.ACCENT, size=20),
            trailing=trailing
            or ft.Icon(ft.Icons.CHEVRON_RIGHT, color=theme.MUTED, size=20),
            on_click=on_click,
        )

    # ── HOME ──────────────────────────────────────────────────────────────
    def _build_home(self, data: dict[str, Any]) -> list[ft.Control]:
        controls: list[ft.Control] = []

        controls.append(
            ft.Container(
                content=ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(
                                ft.Icons.PLAY_ARROW, color=theme.BG, size=32
                            ),
                            width=56,
                            height=56,
                            bgcolor=theme.PRIMARY,
                            border_radius=18,
                            alignment=ft.alignment.center,
                        ),
                        ft.Column(
                            [
                                ft.Text(
                                    "OSTE Mobile",
                                    size=24,
                                    weight=ft.FontWeight.BOLD,
                                    color=theme.TEXT,
                                ),
                                theme.muted(
                                    "Downloader & streamer — interfaccia Android"
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=14,
                ),
                bgcolor=theme.SURFACE,
                border_radius=22,
                padding=ft.padding.all(18),
            )
        )

        self._home_query = ft.TextField(
            hint_text="Cerca un titolo su tutti i servizi…",
            prefix_icon=ft.Icons.SEARCH,
            filled=True,
            bgcolor=theme.SURFACE_ALT,
            border_radius=14,
            border_color=ft.Colors.TRANSPARENT,
            on_submit=lambda e: self._submit_home_search(),
        )
        self._home_sector = ft.Dropdown(
            value=self._sector,
            options=[ft.dropdown.Option(key, label) for key, label in SECTORS],
            filled=True,
            bgcolor=theme.SURFACE_ALT,
            border_radius=14,
            border_color=ft.Colors.TRANSPARENT,
            expand=True,
            on_change=self._on_sector_change,
        )
        controls.append(
            theme.card(
                ft.Column(
                    [
                        self._home_query,
                        ft.Row(
                            [
                                self._home_sector,
                                ft.FilledButton(
                                    "Cerca",
                                    icon=ft.Icons.SEARCH,
                                    on_click=lambda e: self._submit_home_search(),
                                ),
                            ],
                            spacing=10,
                        ),
                    ],
                    spacing=10,
                )
            )
        )

        controls.append(theme.section_title("Servizi"))
        try:
            providers = core.all_providers()
        except Exception as exc:
            controls.append(
                self._error_card(
                    "Impossibile caricare il motore StreamingCommunity.\n"
                    f"Dettaglio: {exc}"
                )
            )
            return controls

        cards = [self._provider_card(provider) for provider in providers]
        controls.append(
            ft.ResponsiveRow(
                cards,
                spacing=10,
                run_spacing=10,
            )
        )
        controls.append(
            ft.Text(
                "L'app riusa i provider del progetto StreamingCommunity. "
                "Scarica solo contenuti che sei autorizzato a scaricare.",
                size=10,
                color=theme.MUTED,
                text_align=ft.TextAlign.CENTER,
            )
        )
        return controls

    def _provider_card(self, provider: Any) -> ft.Container:
        return ft.Container(
            col={"xs": 6, "sm": 4, "md": 3},
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Icon(core.provider_icon(provider), color=theme.PRIMARY, size=26),
                        width=46,
                        height=46,
                        bgcolor=theme.SURFACE_HI,
                        border_radius=14,
                        alignment=ft.alignment.center,
                    ),
                    ft.Text(
                        getattr(provider, "name", "Servizio"),
                        size=13,
                        weight=ft.FontWeight.W_600,
                        color=theme.TEXT,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    theme.muted(core.provider_kind_label(provider), size=10),
                ],
                spacing=8,
            ),
            bgcolor=theme.SURFACE,
            border_radius=16,
            padding=ft.padding.all(12),
            ink=True,
            on_click=lambda e, p=provider: self._open_provider_search(p),
        )

    def _on_sector_change(self, event: ft.ControlEvent) -> None:
        self._sector = str(event.control.value or "all")

    def _submit_home_search(self) -> None:
        query = (self._home_query.value if self._home_query else "") or ""
        sector = (self._home_sector.value if self._home_sector else self._sector) or "all"
        self._start_global(query, sector)

    # ── provider search ───────────────────────────────────────────────────
    def _open_provider_search(self, provider: Any) -> None:
        self._push(
            View(
                "search",
                getattr(provider, "name", "Cerca"),
                {
                    "provider": provider,
                    "query": "",
                    "entries": [],
                    "error": None,
                    "loading": False,
                    "searched": False,
                    "gen": 0,
                },
            )
        )

    def _build_search(self, data: dict[str, Any]) -> list[ft.Control]:
        provider = data["provider"]
        controls: list[ft.Control] = [self._provider_header(provider)]

        query = ft.TextField(
            value=data.get("query", ""),
            hint_text=f"Cerca su {getattr(provider, 'name', '')}…",
            prefix_icon=ft.Icons.SEARCH,
            filled=True,
            bgcolor=theme.SURFACE_ALT,
            border_radius=14,
            border_color=ft.Colors.TRANSPARENT,
            expand=True,
            autofocus=not data.get("searched") and not data.get("loading"),
            on_submit=lambda e: self._start_provider_search(data, query.value),
        )
        controls.append(
            ft.Row(
                [
                    query,
                    ft.IconButton(
                        icon=ft.Icons.SEARCH,
                        icon_color=theme.PRIMARY,
                        tooltip="Cerca",
                        on_click=lambda e: self._start_provider_search(data, query.value),
                    ),
                ],
                spacing=6,
            )
        )

        if data.get("loading"):
            controls.append(
                theme.card(
                    ft.Row(
                        [
                            ft.ProgressBar(expand=True, color=theme.PRIMARY),
                            theme.muted("Ricerca in corso…"),
                        ],
                        spacing=12,
                    )
                )
            )
        elif data.get("error"):
            controls.append(self._error_card(str(data["error"])))
        elif data.get("searched") and not data.get("entries"):
            controls.append(self._empty("Nessun risultato trovato.", "SEARCH_OFF"))
        elif data.get("entries"):
            controls.append(theme.section_title(f"Risultati ({len(data['entries'])})"))
            controls.extend(
                self._entry_card(provider, entry) for entry in data["entries"]
            )
        return controls

    def _start_provider_search(self, data: dict[str, Any], query: str) -> None:
        query = (query or "").strip()
        if not query:
            self._toast("Inserisci un titolo da cercare.")
            return
        provider = data["provider"]
        data.update(
            query=query,
            entries=[],
            error=None,
            loading=True,
            searched=False,
            gen=int(data.get("gen", 0)) + 1,
        )
        gen = data["gen"]
        self._render()

        def worker() -> None:
            try:
                entries = list(provider.search(query))
                error = None
            except Exception as exc:
                entries = []
                error = str(exc) or exc.__class__.__name__
            self._post(self._finish_provider_search, data, gen, entries, error)

        self.page.run_thread(worker)

    async def _finish_provider_search(
        self,
        data: dict[str, Any],
        gen: int,
        entries: list[Any],
        error: str | None,
    ) -> None:
        if data.get("gen") != gen:
            return
        data.update(
            entries=entries,
            error=error,
            loading=False,
            searched=True,
        )
        if self._view_is(data):
            self._render()

    # ── global search ─────────────────────────────────────────────────────
    def _start_global(self, query: str, sector: str) -> None:
        query = (query or "").strip()
        if not query:
            self._toast("Inserisci un titolo da cercare.")
            return
        self._sector = sector or "all"
        data: dict[str, Any] = {
            "query": query,
            "sector": self._sector,
            "results": {},
            "errors": [],
            "loading": True,
            "gen": 0,
        }
        data["gen"] = int(data.get("gen", 0)) + 1
        gen = data["gen"]
        self._push(View("global", f"Ricerca: {query}", data))

        try:
            from StreamingCommunity.cli.tui.global_search import (
                aggregate_search,
                providers_for_sector,
            )

            providers = providers_for_sector(self._sector)
        except Exception as exc:
            data.update(loading=False, errors=[str(exc)])
            self._render()
            return

        if not providers:
            data["loading"] = False
            self._render()
            return

        def worker() -> None:
            try:
                for provider, entries, error in aggregate_search(providers, query):
                    self._post(self._global_result, data, gen, provider, entries, error)
            except Exception as exc:
                self._post(self._global_error, data, gen, str(exc))
            finally:
                self._post(self._global_done, data, gen)

        self.page.run_thread(worker)

    async def _global_result(
        self,
        data: dict[str, Any],
        gen: int,
        provider: Any,
        entries: list[Any],
        error: BaseException | None,
    ) -> None:
        if data.get("gen") != gen:
            return
        if error is not None:
            data["errors"].append(str(error) or error.__class__.__name__)
        elif entries:
            data["results"][getattr(provider, "alias", getattr(provider, "name", "?"))] = (
                provider,
                entries,
            )
        if self._view_is(data):
            self._render()

    async def _global_error(
        self, data: dict[str, Any], gen: int, message: str
    ) -> None:
        if data.get("gen") != gen:
            return
        data["errors"].append(message)
        if self._view_is(data):
            self._render()

    async def _global_done(self, data: dict[str, Any], gen: int) -> None:
        if data.get("gen") != gen:
            return
        data["loading"] = False
        if self._view_is(data):
            self._render()

    def _build_global(self, data: dict[str, Any]) -> list[ft.Control]:
        controls: list[ft.Control] = []
        results: dict[str, tuple[Any, list[Any]]] = data.get("results", {})
        total = sum(len(entries) for _, entries in results.values())

        if data.get("loading"):
            controls.append(
                theme.card(
                    ft.Row(
                        [
                            ft.ProgressBar(expand=True, color=theme.PRIMARY),
                            theme.muted("Ricerca in corso…"),
                        ],
                        spacing=12,
                    )
                )
            )

        if data.get("errors"):
            controls.append(
                theme.card(
                    ft.Text(
                        "Alcuni servizi non hanno risposto: "
                        + ", ".join(data["errors"]),
                        size=11,
                        color=theme.YELLOW,
                    ),
                    bgcolor=ft.Colors.with_opacity(0.10, theme.YELLOW),
                )
            )

        if not results and not data.get("loading"):
            controls.append(
                self._empty(
                    f"Nessun risultato per «{data.get('query', '')}».", "SEARCH_OFF"
                )
            )
            return controls

        for provider, entries in results.values():
            controls.append(
                ft.Row(
                    [
                        ft.Icon(core.provider_icon(provider), color=theme.ACCENT, size=18),
                        theme.section_title(getattr(provider, "name", "Servizio")),
                        theme.muted(f"({len(entries)})", size=11),
                    ],
                    spacing=8,
                )
            )
            controls.extend(
                self._entry_card(provider, entry) for entry in entries
            )

        if total:
            controls.append(theme.muted(f"{total} risultati", size=11))
        return controls

    # ── detail ────────────────────────────────────────────────────────────
    def _open_entry(self, provider: Any, entry: Any) -> None:
        if getattr(provider, "flow", "") == "music":
            self._music_pick(provider, entry)
            return
        try:
            is_series = bool(provider.is_series(entry))
        except Exception:
            is_series = bool(getattr(provider, "supports_seasons", False))
        data: dict[str, Any] = {
            "provider": provider,
            "entry": entry,
            "is_series": is_series,
            "description": str(
                getattr(entry, "desc", "")
                or getattr(entry, "description", "")
                or getattr(entry, "overview", "")
                or ""
            ).strip(),
            "desc_started": False,
            "desc_loading": False,
        }
        self._push(View("detail", core.entry_name(entry), data))
        self._load_description(data)

    def _load_description(self, data: dict[str, Any]) -> None:
        if data.get("desc_started"):
            return
        provider = data["provider"]
        fetch = getattr(provider, "entry_description", None)
        if not callable(fetch):
            return
        data["desc_started"] = True
        data["desc_loading"] = True
        entry = data["entry"]
        self._render()

        def worker() -> None:
            try:
                text = fetch(entry)
            except Exception:
                text = None
            self._post(self._finish_description, data, text)

        self.page.run_thread(worker)

    async def _finish_description(
        self, data: dict[str, Any], text: Any
    ) -> None:
        data["desc_loading"] = False
        if text:
            data["description"] = str(text)
        if self._view_is(data):
            self._render()

    def _build_detail(self, data: dict[str, Any]) -> list[ft.Control]:
        provider = data["provider"]
        entry = data["entry"]
        is_series = bool(data.get("is_series"))
        controls: list[ft.Control] = []

        icon, kind = core.media_badge(provider, is_series)
        badges = [theme.badge(f"{icon} {kind}", theme.GREEN)]
        badges.append(theme.badge(str(getattr(provider, "name", "")), theme.ACCENT))
        year = getattr(entry, "year", None)
        if year:
            badges.append(theme.badge(str(year), theme.PRIMARY))
        language = getattr(entry, "provider_language", None)
        if language:
            badges.append(theme.badge(str(language), theme.YELLOW))

        controls.append(
            theme.card(
                ft.Column(
                    [
                        ft.Text(
                            core.entry_name(entry),
                            size=20,
                            weight=ft.FontWeight.BOLD,
                            color=theme.TEXT,
                        ),
                        ft.Row(badges, wrap=True, spacing=6, run_spacing=6),
                        ft.Text(
                            data.get("description") or "",
                            size=12,
                            color=theme.MUTED,
                            visible=bool(data.get("description")),
                        ),
                        ft.Row(
                            [
                                ft.ProgressBar(
                                    width=80,
                                    color=theme.PRIMARY,
                                ),
                                theme.muted("Carico trama…"),
                            ],
                            spacing=10,
                            visible=bool(data.get("desc_loading")),
                        ),
                    ],
                    spacing=10,
                )
            )
        )

        pairs = core.entry_pairs(provider, entry)
        if pairs:
            rows = [
                ft.Row(
                    [
                        ft.Text(label, size=11, color=theme.MUTED, width=100),
                        ft.Text(value, size=12, color=theme.TEXT, expand=True),
                    ],
                    spacing=8,
                )
                for label, value in pairs
            ]
            controls.append(
                theme.card(
                    ft.Column(
                        [theme.section_title("Informazioni"), *rows],
                        spacing=8,
                    )
                )
            )

        actions: list[ft.Control] = []
        if is_series and getattr(provider, "supports_seasons", True):
            label = "Apri volumi" if getattr(provider, "alias", "") == "mangaworld" else "Apri stagioni"
            actions.append(
                ft.FilledButton(
                    label,
                    icon=ft.Icons.SUBSCRIPTIONS,
                    on_click=lambda e: self._open_seasons(data),
                )
            )
        else:
            if getattr(provider, "alias", "") == "torrent":
                label = "Scarica torrent"
            elif getattr(provider, "category", "") == "Books":
                label = "Scarica libro"
            else:
                label = "Scarica"
            actions.append(
                ft.FilledButton(
                    label,
                    icon=ft.Icons.DOWNLOAD,
                    on_click=lambda e: self._enqueue_atomic(data),
                )
            )
            if getattr(provider, "supports_streaming", False):
                actions.append(
                    ft.OutlinedButton(
                        "Streaming",
                        icon=ft.Icons.CAST,
                        on_click=lambda e: self._enqueue_stream(data),
                    )
                )

        actions.append(
            ft.Text(
                "I download continuano in background nella scheda Download.",
                size=10,
                color=theme.MUTED,
            )
        )
        controls.append(theme.card(ft.Column(actions, spacing=10)))
        return controls

    def _enqueue_atomic(self, data: dict[str, Any]) -> None:
        provider = data["provider"]
        entry = data["entry"]
        kind = str(getattr(provider, "queue_kind", "") or "")
        if not kind:
            kind = "book" if getattr(provider, "category", "") == "Books" else "film"
        self._enqueue_items(
            provider,
            [
                {
                    "kind": kind,
                    "label": core.entry_name(entry),
                    "mode": "download",
                    "entry": entry,
                }
            ],
            "Aggiunto alla coda.",
        )

    def _enqueue_stream(self, data: dict[str, Any]) -> None:
        provider = data["provider"]
        entry = data["entry"]
        self._enqueue_items(
            provider,
            [
                {
                    "kind": "film",
                    "label": f"Streaming · {core.entry_name(entry)}",
                    "mode": "stream",
                    "entry": entry,
                }
            ],
            "Streaming avviato sul dispositivo.",
        )

    # ── seasons / volumes ─────────────────────────────────────────────────
    def _open_seasons(self, detail: dict[str, Any]) -> None:
        provider = detail["provider"]
        entry = detail["entry"]
        data: dict[str, Any] = {
            "provider": provider,
            "entry": entry,
            "scraper": None,
            "seasons": [],
            "loading": True,
            "error": None,
        }
        is_manga = getattr(provider, "alias", "") == "mangaworld"
        self._push(
            View("seasons", "Volumi" if is_manga else "Stagioni", data)
        )

        def worker() -> None:
            try:
                scraper = provider.new_series_scraper(entry)
                seasons = list(provider.seasons(scraper))
                error = None
            except Exception as exc:
                scraper = None
                seasons = []
                error = str(exc) or exc.__class__.__name__
            self._post(self._finish_seasons, data, scraper, seasons, error)

        self.page.run_thread(worker)

    async def _finish_seasons(
        self,
        data: dict[str, Any],
        scraper: Any,
        seasons: list[Any],
        error: str | None,
    ) -> None:
        data.update(scraper=scraper, seasons=seasons, loading=False, error=error)
        if self._view_is(data):
            self._render()

    def _build_seasons(self, data: dict[str, Any]) -> list[ft.Control]:
        controls: list[ft.Control] = [self._provider_header(data["provider"])]
        if data.get("loading"):
            controls.append(
                theme.card(
                    ft.Row(
                        [
                            ft.ProgressBar(expand=True, color=theme.PRIMARY),
                            theme.muted("Carico l'elenco…"),
                        ],
                        spacing=12,
                    )
                )
            )
            return controls
        if data.get("error"):
            controls.append(self._error_card(str(data["error"])))
            return controls

        seasons = data.get("seasons") or []
        if not seasons:
            controls.append(self._empty("Nessuna stagione disponibile.", "SUBSCRIPTIONS"))
            return controls

        is_manga = getattr(data["provider"], "alias", "") == "mangaworld"
        controls.append(theme.section_title("Volumi" if is_manga else "Stagioni"))
        for index, season in enumerate(seasons):
            number = core.format_number(
                getattr(season, "number", None) or index + 1
            )
            name = str(getattr(season, "name", "") or "")
            prefix = "Volume" if is_manga else "Stagione"
            controls.append(
                self._list_card(
                    f"{prefix} {number}",
                    name,
                    leading=ft.Icon(
                        ft.Icons.MENU_BOOK if is_manga else ft.Icons.VIDEO_LIBRARY,
                        color=theme.ACCENT,
                        size=20,
                    ),
                    on_click=lambda e, i=index: self._open_episodes(data, i),
                )
            )
        return controls

    # ── episodes / chapters ───────────────────────────────────────────────
    def _open_episodes(self, season_data: dict[str, Any], index: int) -> None:
        provider = season_data["provider"]
        seasons = season_data.get("seasons") or []
        if not 0 <= index < len(seasons):
            return
        season_obj = seasons[index]
        season_number = core.to_int(
            getattr(season_obj, "number", None), index + 1
        )
        is_manga = getattr(provider, "alias", "") == "mangaworld"
        data: dict[str, Any] = {
            "provider": provider,
            "entry": season_data["entry"],
            "scraper": season_data.get("scraper"),
            "season": season_number,
            "season_index": index,
            "season_name": str(getattr(season_obj, "name", "") or ""),
            "episodes": [],
            "loading": True,
            "error": None,
        }
        title = f"{'Volume' if is_manga else 'Stagione'} {core.format_number(season_number)}"
        self._push(View("episodes", title, data))

        def worker() -> None:
            try:
                episodes = list(provider.episodes(data["scraper"], season_number))
                error = None
            except Exception as exc:
                episodes = []
                error = str(exc) or exc.__class__.__name__
            self._post(self._finish_episodes, data, episodes, error)

        self.page.run_thread(worker)

    async def _finish_episodes(
        self,
        data: dict[str, Any],
        episodes: list[Any],
        error: str | None,
    ) -> None:
        data.update(episodes=episodes, loading=False, error=error)
        if self._view_is(data):
            self._render()

    def _build_episodes(self, data: dict[str, Any]) -> list[ft.Control]:
        controls: list[ft.Control] = [self._provider_header(data["provider"])]
        is_manga = getattr(data["provider"], "alias", "") == "mangaworld"

        if data.get("loading"):
            controls.append(
                theme.card(
                    ft.Row(
                        [
                            ft.ProgressBar(expand=True, color=theme.PRIMARY),
                            theme.muted("Carico i contenuti…"),
                        ],
                        spacing=12,
                    )
                )
            )
            return controls
        if data.get("error"):
            controls.append(self._error_card(str(data["error"])))
            return controls

        episodes = data.get("episodes") or []
        if not episodes:
            controls.append(
                self._empty(
                    "Nessun episodio disponibile (potrebbe non essere ancora uscito).",
                    "SUBSCRIPTIONS",
                )
            )
            return controls

        controls.append(
            ft.FilledTonalButton(
                f"Scarica tutti ({len(episodes)})",
                icon=ft.Icons.DOWNLOAD,
                on_click=lambda e: self._enqueue_all_episodes(data),
            )
        )

        for index, episode in enumerate(episodes):
            number = index + 1
            ep_name = core.entry_name(episode)
            subtitle = "" if ep_name == "Sconosciuto" else ep_name
            title = f"{number:02d}" + (f" · {ep_name}" if subtitle else "")
            controls.append(
                self._list_card(
                    title,
                    subtitle,
                    leading=ft.Icon(
                        ft.Icons.MENU_BOOK if is_manga else ft.Icons.PLAY_ARROW,
                        color=theme.ACCENT,
                        size=20,
                    ),
                    trailing=ft.IconButton(
                        icon=ft.Icons.DOWNLOAD,
                        icon_color=theme.PRIMARY,
                        tooltip="Scarica",
                        on_click=lambda e, i=index: self._enqueue_episode(data, i),
                    ),
                )
            )
        return controls

    def _episode_item(self, data: dict[str, Any], index: int) -> dict[str, Any]:
        episodes = data.get("episodes") or []
        episode = episodes[index]
        entry_name = core.entry_name(data["entry"])
        ep_name = core.entry_name(episode)
        season = int(data.get("season") or 1)
        is_manga = getattr(data["provider"], "alias", "") == "mangaworld"
        if is_manga:
            label = f"{entry_name} · V{season} C{index + 1}"
        else:
            label = f"{entry_name} · S{season:02d}E{index + 1:02d}"
        if ep_name and ep_name != "Sconosciuto":
            label += f" · {ep_name}"
        return {
            "kind": "episode",
            "label": label,
            "mode": "download",
            "obj_episode": episode,
            "season": season,
            "episode": index + 1,
            "scraper": data.get("scraper"),
        }

    def _enqueue_episode(self, data: dict[str, Any], index: int) -> None:
        try:
            item = self._episode_item(data, index)
        except IndexError:
            return
        self._enqueue_items(data["provider"], [item], "Episodio in coda.")

    def _enqueue_all_episodes(self, data: dict[str, Any]) -> None:
        count = len(data.get("episodes") or [])
        items = [self._episode_item(data, i) for i in range(count)]
        self._enqueue_items(
            data["provider"], items, f"{count} elementi aggiunti alla coda."
        )

    # ── music ─────────────────────────────────────────────────────────────
    def _music_pick(self, provider: Any, entry: Any) -> None:
        media_type = str(getattr(entry, "type", "") or "").lower()
        if media_type in ("artist", "album"):
            self._open_music_path(provider, entry)
        else:
            self._enqueue_track(provider, entry)

    def _open_music_path(self, provider: Any, entry: Any) -> None:
        data: dict[str, Any] = {
            "provider": provider,
            "parent": entry,
            "level": None,
            "items": [],
            "loading": True,
            "error": None,
        }
        self._push(View("music", core.entry_name(entry), data))

        def worker() -> None:
            try:
                drill = provider.drilldown(entry)
                if drill is None:
                    level, items = None, []
                else:
                    level, items = drill
                error = None
            except Exception as exc:
                level, items = None, []
                error = str(exc) or exc.__class__.__name__
            self._post(self._finish_music, data, level, list(items or []), error)

        self.page.run_thread(worker)

    async def _finish_music(
        self,
        data: dict[str, Any],
        level: str | None,
        items: list[Any],
        error: str | None,
    ) -> None:
        data.update(level=level, items=items, loading=False, error=error)
        if self._view_is(data):
            self._render()

    def _build_music(self, data: dict[str, Any]) -> list[ft.Control]:
        controls: list[ft.Control] = [self._provider_header(data["provider"])]
        if data.get("loading"):
            controls.append(
                theme.card(
                    ft.Row(
                        [
                            ft.ProgressBar(expand=True, color=theme.PRIMARY),
                            theme.muted("Carico la discografia…"),
                        ],
                        spacing=12,
                    )
                )
            )
            return controls
        if data.get("error"):
            controls.append(self._error_card(str(data["error"])))
            return controls

        level = data.get("level")
        items = data.get("items") or []
        if level == "tracks":
            controls.append(
                ft.FilledTonalButton(
                    "Scarica album",
                    icon=ft.Icons.DOWNLOAD,
                    on_click=lambda e: self._enqueue_album(data["provider"], data["parent"]),
                )
            )
        if not items:
            controls.append(self._empty("Nessun contenuto disponibile.", "MUSIC_OFF"))
            return controls

        controls.append(
            theme.section_title("Album" if level == "albums" else "Tracce")
        )
        for item in items:
            if level == "albums":
                controls.append(
                    self._entry_card(
                        data["provider"],
                        item,
                        on_click=lambda e, p=data["provider"], it=item: self._open_music_path(p, it),
                    )
                )
            else:
                controls.append(
                    self._list_card(
                        core.entry_name(item),
                        core.entry_subtitle(data["provider"], item),
                        leading=ft.Icon(ft.Icons.AUDIOTRACK, color=theme.ACCENT, size=20),
                        trailing=ft.IconButton(
                            icon=ft.Icons.DOWNLOAD,
                            icon_color=theme.PRIMARY,
                            tooltip="Scarica",
                            on_click=lambda e, p=data["provider"], it=item: self._enqueue_track(p, it),
                        ),
                    )
                )
        return controls

    def _enqueue_track(self, provider: Any, entry: Any) -> None:
        self._enqueue_items(
            provider,
            [
                {
                    "kind": "track",
                    "label": core.entry_name(entry),
                    "mode": "download",
                    "entry": entry,
                }
            ],
            "Traccia in coda.",
        )

    def _enqueue_album(self, provider: Any, entry: Any) -> None:
        self._enqueue_items(
            provider,
            [
                {
                    "kind": "album",
                    "label": f"Album · {core.entry_name(entry)}",
                    "mode": "download",
                    "entry": entry,
                }
            ],
            "Album in coda.",
        )

    # ── generic queue entry point ─────────────────────────────────────────
    def _enqueue_items(
        self, provider: Any, items: list[dict[str, Any]], message: str
    ) -> None:
        if not items:
            return
        try:
            jobs = self.manager.enqueue(provider, items)
        except Exception as exc:
            self._toast(f"Impossibile accodare: {exc}", error=True)
            return
        if not jobs:
            return
        self._toast(message)
        self._go_downloads()

    # ── downloads ─────────────────────────────────────────────────────────
    def _build_downloads(self, data: dict[str, Any]) -> list[ft.Control]:
        controls: list[ft.Control] = []
        snapshot = self.manager.snapshot()
        data["rows"] = {}

        controls.append(
            ft.Row(
                [
                    theme.section_title(f"Download ({len(snapshot)})"),
                    ft.Container(expand=True),
                    ft.TextButton(
                        "Pulisci",
                        icon=ft.Icons.DELETE,
                        on_click=lambda e: self._clear_downloads(),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )

        if not snapshot:
            controls.append(
                self._empty(
                    "Nessun download. Avvia qualcosa dalla Home.", "DOWNLOAD"
                )
            )
            return controls

        for job in reversed(snapshot):
            controls.append(self._download_row(job, data["rows"]))
        return controls

    def _download_row(
        self, job: dict[str, Any], rows: dict[str, dict[str, Any]]
    ) -> ft.Container:
        status = ft.Text(
            core.job_status_text(job),
            size=11,
            color=theme.ACCENT if job["status"] == "running" else theme.MUTED,
        )
        progress = ft.ProgressBar(
            value=core.job_progress(job),
            color=theme.GREEN if job["status"] == "done" else theme.PRIMARY,
            bgcolor=theme.SURFACE_ALT,
            height=6,
        )
        meta = ft.Text(core.job_meta(job), size=10, color=theme.MUTED, max_lines=1,
                       overflow=ft.TextOverflow.ELLIPSIS)
        cancel = ft.IconButton(
            icon=ft.Icons.CLOSE,
            icon_color=theme.RED,
            icon_size=18,
            tooltip="Annulla",
            visible=job["status"] not in ("done", "failed", "cancelled"),
            on_click=lambda e, job_id=job["id"]: self._cancel_job(job_id),
        )
        icon_name = "DOWNLOAD"
        if job["kind"] == "episode":
            icon_name = "PLAY_ARROW"
        elif job["kind"] in ("track", "album"):
            icon_name = "MUSIC_NOTE"
        elif job["kind"] == "book":
            icon_name = "LOCAL_LIBRARY"

        rows[job["id"]] = {
            "status": status,
            "progress": progress,
            "meta": meta,
            "cancel": cancel,
        }
        return theme.card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(getattr(ft.Icons, icon_name, ft.Icons.DOWNLOAD),
                                    color=theme.PRIMARY, size=20),
                            ft.Column(
                                [
                                    ft.Text(
                                        job["label"],
                                        size=13,
                                        weight=ft.FontWeight.W_600,
                                        color=theme.TEXT,
                                        max_lines=2,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    status,
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            cancel,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                    progress,
                    meta,
                ],
                spacing=6,
            ),
            padding=ft.padding.all(12),
        )

    def _cancel_job(self, job_id: str) -> None:
        self.manager.cancel(job_id)
        self._toast("Annullamento richiesto.")

    def _clear_downloads(self) -> None:
        self.manager.clear_finished()
        self._render()

    async def _ticker(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            try:
                if self._stack and self._stack[-1].kind == "downloads":
                    self._refresh_downloads()
            except Exception:
                pass

    def _refresh_downloads(self) -> None:
        if not self._stack or self._stack[-1].kind != "downloads":
            return
        data = self._stack[-1].data
        rows = data.get("rows") or {}
        snapshot = self.manager.snapshot()
        ids = [job["id"] for job in reversed(snapshot)]
        if ids != list(rows.keys()):
            self._render()
            return

        changed = False
        for job in snapshot:
            row = rows.get(job["id"])
            if row is None:
                continue
            text = core.job_status_text(job)
            if row["status"].value != text:
                row["status"].value = text
                changed = True
            value = core.job_progress(job)
            if row["progress"].value != value:
                row["progress"].value = value
                changed = True
            meta = core.job_meta(job)
            if row["meta"].value != meta:
                row["meta"].value = meta
                changed = True
            visible = job["status"] not in ("done", "failed", "cancelled")
            if row["cancel"].visible != visible:
                row["cancel"].visible = visible
                changed = True
        if changed:
            try:
                self.page.update()
            except Exception:
                pass

    # ── settings ──────────────────────────────────────────────────────────
    def _build_settings(self, data: dict[str, Any]) -> list[ft.Control]:
        controls: list[ft.Control] = [theme.section_title("Impostazioni")]

        try:
            manager = core.config_manager()
            root = manager.config.get("OUTPUT", "root_path")
            check_domain = manager.config.get_bool(
                "DEFAULT", "check_domain_on_start", True
            )
            extension = manager.config.get("PROCESS", "extension")
        except Exception as exc:
            controls.append(self._error_card(f"Configurazione non disponibile: {exc}"))
            manager = None
            root = "Video"
            check_domain = False
            extension = "mkv"

        path_field = ft.TextField(
            label="Cartella di download",
            value=str(root),
            filled=True,
            bgcolor=theme.SURFACE_ALT,
            border_radius=12,
            border_color=ft.Colors.TRANSPARENT,
        )

        def save_path(event: ft.ControlEvent) -> None:
            if manager is None:
                return
            try:
                manager.config.set_key("OUTPUT", "root_path", path_field.value or "Video")
                manager.save_config()
                self._toast("Cartella salvata.")
            except Exception as exc:
                self._toast(f"Errore: {exc}", error=True)

        def toggle_domain(event: ft.ControlEvent) -> None:
            if manager is None:
                return
            try:
                manager.config.set_key(
                    "DEFAULT", "check_domain_on_start", bool(event.control.value)
                )
                manager.save_config()
                self._toast("Preferenza aggiornata.")
            except Exception as exc:
                self._toast(f"Errore: {exc}", error=True)

        controls.append(
            theme.card(
                ft.Column(
                    [
                        path_field,
                        ft.FilledTonalButton(
                            "Salva cartella",
                            icon=ft.Icons.STORAGE,
                            on_click=save_path,
                        ),
                        ft.Divider(color=theme.SURFACE_ALT),
                        ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text(
                                            "Controlla i domini all'avvio",
                                            size=13,
                                            color=theme.TEXT,
                                        ),
                                        theme.muted(
                                            "Aggiorna gli URL dei siti supportati.",
                                            size=10,
                                        ),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                                ft.Switch(
                                    value=check_domain,
                                    active_color=theme.PRIMARY,
                                    on_change=toggle_domain,
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ],
                    spacing=12,
                )
            )
        )

        try:
            providers_count = len(core.all_providers())
        except Exception:
            providers_count = 0
        info = [
            ft.Row(
                [
                    ft.Text("Motore", size=11, color=theme.MUTED, width=110),
                    ft.Text(
                        f"StreamingCommunity {core.core_version()}",
                        size=12,
                        color=theme.TEXT,
                        expand=True,
                    ),
                ]
            ),
            ft.Row(
                [
                    ft.Text("Provider", size=11, color=theme.MUTED, width=110),
                    ft.Text(str(providers_count), size=12, color=theme.TEXT),
                ]
            ),
            ft.Row(
                [
                    ft.Text("Formato", size=11, color=theme.MUTED, width=110),
                    ft.Text(str(extension), size=12, color=theme.TEXT),
                ]
            ),
        ]
        controls.append(theme.card(ft.Column([theme.section_title("Sistema"), *info], spacing=8)))
        controls.append(
            theme.card(
                ft.Text(
                    "Questa interfaccia non incorpora chiavi DRM né aggira paywall. "
                    "Scarica solo contenuti che hai il diritto di accesso a.",
                    size=10,
                    color=theme.MUTED,
                ),
                bgcolor=ft.Colors.with_opacity(0.10, theme.YELLOW),
            )
        )
        return controls
