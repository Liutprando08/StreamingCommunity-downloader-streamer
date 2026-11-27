"""Kivy shell for the headless downloader (Android v1).

Supported services: StreamingCommunity and Altadefinizione.  Both already use
the yt-dlp download engine, so the app only needs a thin UI on top of
:mod:`StreamingCommunity.mobile.api`.
"""

from __future__ import annotations

import os
import threading
import traceback
import uuid

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

# ``prepare`` must run before importing anything that instantiates ConfigManager.
from StreamingCommunity.mobile import bootstrap

PATHS = bootstrap.prepare()

from StreamingCommunity.mobile import api  # noqa: E402  (import order matters)

api.configure()


def _truncate(value: object, limit: int = 160) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


class SearchResultButton(Button):
    def __init__(self, entry: dict, on_pick, **kwargs):
        super().__init__(**kwargs)
        self.entry = entry
        self.size_hint_y = None
        self.height = dp(52)
        self.halign = "left"
        self.valign = "middle"
        self.text_size = (Window.width - dp(40), None)
        label = entry.get("name") or "Untitled"
        year = entry.get("year") or ""
        kind = "Serie" if entry.get("type") == "tv" else "Film"
        self.text = f"{label}  ({year})  ·  {kind}" if year else f"{label}  ·  {kind}"
        self.bind(on_release=lambda *_: on_pick(entry))


class EpisodeButton(Button):
    def __init__(self, season: int, episode: dict, on_pick, **kwargs):
        super().__init__(**kwargs)
        self.season = season
        self.episode = episode
        self.size_hint_y = None
        self.height = dp(44)
        self.halign = "left"
        self.valign = "middle"
        self.text_size = (Window.width - dp(40), None)
        self.text = f"E{episode.get('index')} · {episode.get('name') or ''}"
        self.bind(on_release=lambda *_: on_pick(season, episode))


class MobileRoot(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(6), **kwargs)

        self.service_ids: dict[str, str] = {}
        self.entry: dict | None = None
        self.selection: tuple[int, int] | None = None
        self.seasons: dict[int, list[dict]] = {}
        self.download_id: str | None = None
        self._busy = False

        self._build_header()
        self._build_results()
        self._build_details()
        self._build_download_bar()

        Clock.schedule_interval(self._poll_download, 0.5)

    # ── layout ────────────────────────────────────────────────────────────
    def _build_header(self):
        title = Label(
            text="[b]StreamingCommunity Mobile[/b]",
            markup=True,
            size_hint_y=None,
            height=dp(30),
        )
        self.add_widget(title)

        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        self.service_spinner = Spinner(text="StreamingCommunity")
        for service in api.list_services():
            self.service_ids[service["label"]] = service["id"]
            self.service_spinner.values.append(service["label"])
        row.add_widget(self.service_spinner)

        self.query_input = TextInput(
            hint_text="Cerca un titolo…",
            multiline=False,
            write_tab=False,
        )
        self.query_input.bind(on_text_validate=lambda *_: self.search())
        row.add_widget(self.query_input)

        search_button = Button(text="Cerca", size_hint_x=None, width=dp(80))
        search_button.bind(on_release=lambda *_: self.search())
        row.add_widget(search_button)
        self.add_widget(row)

        self.status = Label(
            text=f"Cartella: {PATHS['output']}",
            size_hint_y=None,
            height=dp(40),
            font_size="12sp",
        )
        self.add_widget(self.status)

    def _build_results(self):
        wrapper = ScrollView(size_hint=(1, 0.34))
        self.results_grid = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        self.results_grid.bind(
            minimum_height=self.results_grid.setter("height")
        )
        wrapper.add_widget(self.results_grid)
        self.add_widget(wrapper)

    def _build_details(self):
        row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        self.season_spinner = Spinner(text="Stagioni", disabled=True)
        self.season_spinner.bind(on_text=self._on_season)
        row.add_widget(self.season_spinner)
        self.add_widget(row)

        wrapper = ScrollView(size_hint=(1, 0.3))
        self.episodes_grid = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        self.episodes_grid.bind(
            minimum_height=self.episodes_grid.setter("height")
        )
        wrapper.add_widget(self.episodes_grid)
        self.add_widget(wrapper)

    def _build_download_bar(self):
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        self.download_button = Button(text="Scarica", disabled=True)
        self.download_button.bind(on_release=lambda *_: self.start_download())
        row.add_widget(self.download_button)

        self.cancel_button = Button(text="Annulla", disabled=True, size_hint_x=None, width=dp(90))
        self.cancel_button.bind(on_release=lambda *_: self.cancel_download())
        row.add_widget(self.cancel_button)
        self.add_widget(row)

        self.progress = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(18))
        self.add_widget(self.progress)

        self.progress_label = Label(
            text="Pronto", size_hint_y=None, height=dp(32), font_size="12sp"
        )
        self.add_widget(self.progress_label)

    # ── helpers ───────────────────────────────────────────────────────────
    def _service_id(self) -> str:
        return self.service_ids.get(self.service_spinner.text, "streamingcommunity")

    def _set_status(self, message: object):
        self.status.text = _truncate(message, 220)

    def _set_busy(self, busy: bool):
        self._busy = busy
        self.download_button.disabled = busy or self.entry is None
        self.cancel_button.disabled = not busy or not self.download_id

    def _run_bg(self, func, on_success, on_error=None):
        if self._busy:
            return

        self._set_busy(True)

        def worker():
            try:
                result = func()
            except Exception as exc:  # surface to the UI thread
                traceback.print_exc()
                Clock.schedule_once(
                    lambda *_: self._finish_bg(None, exc, on_success, on_error), 0
                )
                return

            Clock.schedule_once(
                lambda *_: self._finish_bg(result, None, on_success, on_error), 0
            )

        threading.Thread(target=worker, daemon=True).start()

    def _finish_bg(self, result, error, on_success, on_error):
        self._set_busy(False)
        if error is not None:
            if on_error:
                on_error(error)
            else:
                self._set_status(f"Errore: {error}")
            return
        on_success(result)

    # ── search ────────────────────────────────────────────────────────────
    def search(self):
        query = self.query_input.text.strip()
        if not query:
            self._set_status("Inserisci un titolo da cercare.")
            return

        service = self._service_id()
        self._set_status("Ricerca in corso…")
        self._run_bg(
            lambda: api.search(service, query),
            self._render_results,
            lambda exc: self._set_status(f"Ricerca fallita: {exc}"),
        )

    def _render_results(self, entries: list[dict]):
        self.results_grid.clear_widgets()
        self.entry = None
        self.selection = None
        self.seasons.clear()
        self.season_spinner.values = []
        self.season_spinner.text = "Stagioni"
        self.season_spinner.disabled = True
        self.episodes_grid.clear_widgets()
        self.download_button.disabled = True

        if not entries:
            self._set_status("Nessun risultato.")
            return

        for entry in entries:
            self.results_grid.add_widget(
                SearchResultButton(entry, self._on_entry)
            )
        self._set_status(f"{len(entries)} risultati. Seleziona un titolo.")

    def _on_entry(self, entry: dict):
        self.entry = entry
        self.selection = None
        self.seasons.clear()
        self.episodes_grid.clear_widgets()
        self.season_spinner.values = []
        self.season_spinner.disabled = True
        self.download_button.disabled = True

        if entry.get("type") != "tv":
            self.download_button.disabled = False
            self._set_status(f"Film selezionato: {entry.get('name')}")
            return

        self._set_status(f"Carico le stagioni di {entry.get('name')}…")
        service = self._service_id()
        self._run_bg(
            lambda: api.get_details(service, entry),
            self._render_series,
            lambda exc: self._set_status(f"Stagioni non disponibili: {exc}"),
        )

    def _render_series(self, details: dict):
        seasons = details.get("seasons") or []
        if not seasons:
            self._set_status("Nessuna stagione trovata.")
            return

        labels = []
        for season in seasons:
            number = season.get("number")
            self.seasons[number] = season.get("episodes") or []
            labels.append(f"S{number}")

        self.season_spinner.values = labels
        self.season_spinner.disabled = False
        self.season_spinner.text = labels[0]
        self._render_episodes(seasons[0].get("number"))
        self._set_status(f"{len(seasons)} stagioni disponibili.")

    def _on_season(self, _spinner, text: str):
        if not text.startswith("S"):
            return
        try:
            number = int(text[1:])
        except ValueError:
            return
        self._render_episodes(number)

    def _render_episodes(self, season_number):
        self.episodes_grid.clear_widgets()
        self.selection = None
        self.download_button.disabled = True

        episodes = self.seasons.get(season_number, [])
        for episode in episodes:
            self.episodes_grid.add_widget(
                EpisodeButton(season_number, episode, self._on_episode)
            )
        if not episodes:
            self._set_status("Nessun episodio per questa stagione.")

    def _on_episode(self, season: int, episode: dict):
        self.selection = (season, int(episode.get("index")))
        self.download_button.disabled = False
        self._set_status(
            f"Selezionato S{season}E{self.selection[1]}: {episode.get('name')}"
        )

    # ── download ──────────────────────────────────────────────────────────
    def start_download(self):
        if not self.entry:
            return

        season = episode = None
        if self.selection:
            season, episode = self.selection

        self.download_id = uuid.uuid4().hex[:12]
        service = self._service_id()
        entry = self.entry
        download_id = self.download_id
        self.progress.value = 0
        self.progress_label.text = "Avvio download…"
        self._set_busy(True)
        self.cancel_button.disabled = False

        def worker():
            try:
                result = api.download(
                    service,
                    entry,
                    season=season,
                    episode=episode,
                    download_id=download_id,
                )
            except Exception as exc:
                traceback.print_exc()
                Clock.schedule_once(lambda *_: self._download_finished({
                    "success": False,
                    "error": str(exc),
                }), 0)
                return

            Clock.schedule_once(lambda *_: self._download_finished(result), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _download_finished(self, result: dict):
        self._busy = False
        self.download_button.disabled = self.entry is None
        self.cancel_button.disabled = True

        if result.get("success"):
            self.progress.value = 100
            self.progress_label.text = f"Completato: {result.get('path')}"
            self._set_status(f"Salvato in {result.get('path')}")
        else:
            self.progress_label.text = f"Fallito: {result.get('error') or 'errore'}"
            self._set_status(f"Download fallito: {result.get('error') or 'errore'}")

    def cancel_download(self):
        if self.download_id:
            api.cancel(self.download_id)
            self._set_status("Annullamento richiesto…")

    def _poll_download(self, _dt):
        if not self.download_id:
            return

        state = api.download_state(self.download_id)
        if not state:
            return

        try:
            self.progress.value = float(state.get("progress") or 0)
        except (TypeError, ValueError):
            self.progress.value = 0

        parts = [
            str(state.get("status") or ""),
            f"{self.progress.value:.1f}%",
            str(state.get("speed") or ""),
            str(state.get("size") or ""),
        ]
        self.progress_label.text = " · ".join(part for part in parts if part)


class StreamingCommunityMobileApp(App):
    title = "StreamingCommunity"

    def build(self):
        Window.clearcolor = (0.08, 0.08, 0.1, 1)
        return MobileRoot()


def main():
    StreamingCommunityMobileApp().run()


if __name__ == "__main__":
    main()
