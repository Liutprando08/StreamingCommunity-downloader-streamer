# Settings screen: browse and edit every JSON file under Conf/.
#
# Each tab is one configuration file. The tree on the left mirrors the JSON
# structure (sections → keys, arbitrarily nested); selecting a leaf loads it
# into the editor, "Applica" writes it to the in-memory config (and clears the
# ConfigManager cache), "Salva file" persists it with the matching save_*
# method. Values keep their original type: booleans use a switch, lists are
# edited as JSON so commas inside items stay unambiguous.

from __future__ import annotations

import json
from typing import Any

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Input,
    Label,
    Static,
    Switch,
    Tab,
    Tabs,
    Tree,
)

from StreamingCommunity.utils import config_manager

from ..widgets import Header

# (tab id, tab label, ConfigManager accessor attribute, save method name)
CONFIG_FILES: tuple[tuple[str, str, str, str], ...] = (
    ("config", "config.json", "config", "save_config"),
    ("login", "login.json", "login", "save_login"),
    ("domains", "domains.json", "domain", "save_domains"),
    ("remote_cdm", "remote_cdm.json", "remote_cdm", "save_remote_cdm"),
)

_MAX_PREVIEW = 70


class SettingsScreen(Screen):
    BINDINGS = [("escape", "back", "Indietro")]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._file_id = CONFIG_FILES[0][0]
        self._path: tuple[str, ...] | None = None
        self._node: Any = None
        self._dirty = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="settings-root"):
            yield Label("[bold #89dceb]Impostazioni[/]", id="settings-title")
            yield Tabs(
                *[Tab(label, id=file_id) for file_id, label, *_ in CONFIG_FILES],
                id="settings-tabs",
            )
            with Horizontal(id="settings-body"):
                with Container(classes="settings-box"):
                    yield Tree("config.json", id="settings-tree")
                with Vertical(id="settings-editor"):
                    yield Label("Seleziona una voce", id="settings-path")
                    yield Input(placeholder="Valore", id="settings-value")
                    yield Switch(id="settings-switch")
                    with Horizontal(id="settings-editor-actions"):
                        yield Button("Applica", variant="primary", id="settings-apply")
                        yield Button("Annulla", id="settings-reset")
                    yield Static(
                        "[dim]Le liste si modificano come JSON: [\"a\", \"b\"][/]",
                        id="settings-hint",
                    )
            with Horizontal(id="settings-actions"):
                yield Button("Salva file", variant="success", id="settings-save")
                yield Button("Ricarica", id="settings-reload")
                yield Button("Indietro", id="settings-back")
            yield Static("", id="settings-status")
        yield Footer()

    def on_mount(self) -> None:
        self._reset_editor()
        self._build_tree()
        self._set_status(f"[dim]File: {self._file_label()}[/]")

    # ── current file ──────────────────────────────────────────────────────
    def _spec(self) -> tuple[str, str, str]:
        for file_id, label, accessor, save_method in CONFIG_FILES:
            if file_id == self._file_id:
                return label, accessor, save_method
        return CONFIG_FILES[0][1], CONFIG_FILES[0][2], CONFIG_FILES[0][3]

    def _file_label(self) -> str:
        return self._spec()[0]

    def _data(self) -> dict:
        accessor = self._spec()[1]
        return getattr(config_manager, accessor)._config_dict

    # ── status / editor helpers ───────────────────────────────────────────
    def _set_status(self, text: str) -> None:
        self.query_one("#settings-status", Static).update(text)

    def _reset_editor(self) -> None:
        self._path = None
        self._node = None
        self.query_one("#settings-path", Label).update(
            "Seleziona una voce da modificare"
        )
        value_input = self.query_one("#settings-value", Input)
        value_input.value = ""
        value_input.display = True
        value_input.disabled = True
        self.query_one("#settings-switch", Switch).display = False
        self.query_one("#settings-apply", Button).disabled = True

    def _load_editor(self, path: tuple[str, ...], value: Any) -> None:
        value_input = self.query_one("#settings-value", Input)
        switch = self.query_one("#settings-switch", Switch)
        apply_button = self.query_one("#settings-apply", Button)

        type_name = "sezione" if isinstance(value, dict) else type(value).__name__
        self.query_one("#settings-path", Label).update(
            f"[b]{' › '.join(path)}[/]  [dim]({type_name})[/]"
        )

        if isinstance(value, dict):
            value_input.display = False
            switch.display = False
            apply_button.disabled = True
            return

        apply_button.disabled = False
        if isinstance(value, bool):
            value_input.display = False
            switch.display = True
            switch.value = value
        else:
            value_input.display = True
            value_input.disabled = False
            switch.display = False
            if isinstance(value, list):
                value_input.value = json.dumps(value, ensure_ascii=False)
            else:
                value_input.value = "" if value is None else str(value)

    # ── tree ──────────────────────────────────────────────────────────────
    def _build_tree(self) -> None:
        tree = self.query_one("#settings-tree", Tree)
        tree.reset(self._file_label())
        self._populate(tree.root, self._data(), ())
        tree.root.expand()
        self._reset_editor()

    def _populate(self, node: Any, data: dict, path: tuple[str, ...]) -> None:
        for key, value in data.items():
            full_path = path + (str(key),)
            if isinstance(value, dict):
                child = node.add(str(key), data=(full_path, value), expand=False)
                self._populate(child, value, full_path)
            else:
                node.add_leaf(f"{key}: {self._format(value)}", data=(full_path, value))

    @staticmethod
    def _format(value: Any) -> str:
        if isinstance(value, bool):
            text = "true" if value else "false"
        elif isinstance(value, list):
            text = json.dumps(value, ensure_ascii=False)
        else:
            text = str(value)
        return text if len(text) <= 60 else text[:57] + "..."

    # ── file switching ────────────────────────────────────────────────────
    @on(Tabs.TabActivated, "#settings-tabs")
    def _on_file_tab(self, event: Tabs.TabActivated) -> None:
        tab = event.tab
        if tab is None or tab.id is None:
            return
        self._file_id = tab.id
        self._build_tree()
        self._set_status(f"[dim]File: {self._file_label()}[/]")

    # ── selection ─────────────────────────────────────────────────────────
    @on(Tree.NodeHighlighted, "#settings-tree")
    @on(Tree.NodeSelected, "#settings-tree")
    def _on_node(self, event) -> None:
        data = event.node.data
        if not data:
            self._reset_editor()
            return
        path, value = data
        self._path = path
        self._node = event.node
        self._load_editor(path, value)

    # ── editing ───────────────────────────────────────────────────────────
    def _read_value(self, original: Any) -> Any:
        if isinstance(original, bool):
            return self.query_one("#settings-switch", Switch).value
        text = self.query_one("#settings-value", Input).value
        if isinstance(original, int):
            return int(text.strip())
        if isinstance(original, float):
            return float(text.strip())
        if isinstance(original, list):
            parsed = json.loads(text)
            if not isinstance(parsed, list):
                raise ValueError('atteso un elenco JSON, es. ["a", "b"]')
            return parsed
        if original is None:
            return None if text.strip().lower() == "null" else text
        return text

    @on(Button.Pressed, "#settings-apply")
    def _apply(self) -> None:
        if not self._path or self._node is None:
            self._set_status("[#f9e2af]Seleziona una voce da modificare.")
            return
        original = self._node.data[1]
        if isinstance(original, dict):
            self._set_status("[#f9e2af]Seleziona un valore, non una sezione.")
            return
        try:
            value = self._read_value(original)
        except (ValueError, json.JSONDecodeError) as exc:
            self._set_status(f"[#f38ba8]Valore non valido: {exc}")
            return

        node = self._data()
        for key in self._path[:-1]:
            node = node[key]
        node[self._path[-1]] = value

        # Drop cached reads so every accessor sees the new value immediately.
        config_manager.cache.clear()

        self._node.data = (self._path, value)
        self._node.set_label(f"{self._path[-1]}: {self._format(value)}")
        self._dirty = True
        self._set_status(
            f"[#a6e3a1]Aggiornato {' › '.join(self._path)}. Ricorda di salvare.[/]"
        )

    @on(Button.Pressed, "#settings-reset")
    def _reset_value(self) -> None:
        if self._node is None or not self._node.data:
            self._set_status("[#f9e2af]Nessuna voce selezionata.")
            return
        path, value = self._node.data
        self._load_editor(path, value)
        self._set_status("[dim]Valore ripristinato.[/]")

    # ── persistence ───────────────────────────────────────────────────────
    @on(Button.Pressed, "#settings-save")
    def _save(self) -> None:
        label, _, save_method = self._spec()
        save_fn = getattr(config_manager, save_method, None)
        if save_fn is None:
            self._set_status("[#f38ba8]Salvataggio non disponibile per questo file.")
            return
        try:
            save_fn()
        except Exception as exc:  # noqa: BLE001 - surface any write error to the UI
            self._set_status(f"[#f38ba8]Errore durante il salvataggio: {exc}")
            return
        self._dirty = False
        self._set_status(f"[#a6e3a1]{label} salvato.[/]")

    @on(Button.Pressed, "#settings-reload")
    def _reload(self) -> None:
        config_manager.load_all_configs()
        config_manager.cache.clear()
        self._build_tree()
        self._set_status("[#a6e3a1]Configurazioni ricaricate da disco.[/]")

    @on(Button.Pressed, "#settings-back")
    def _back_button(self) -> None:
        self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()
