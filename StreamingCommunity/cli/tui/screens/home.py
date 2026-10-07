from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Footer, OptionList, Static

from ..providers import registry
from ..widgets import Header
from .search import SearchScreen

HOME_MARKUP = (
    "[b][magenta] ██████╗ ███████╗████████╗███████╗[/]\n"
    "[b][magenta]██╔═══██╗██╔════╝╚══██╔══╝██╔════╝[/]\n"
    "[b][magenta]██║   ██║███████╗   ██║   █████╗  [/]\n"
    "[b][magenta]██║   ██║╚════██║   ██║   ██╔══╝  [/]\n"
    "[b][magenta] ██████╔╝███████║   ██║   ███████╗[/]\n"
    "[b][magenta]  ╚════╝ ╚══════╝   ╚═╝   ╚══════╝[/]\n\n"
    "[i][dim]I'm gonna be king of the pirates[/]"
)


class HomeScreen(Screen):
    BINDINGS = [("d", "toggle_dark", "Toggle dark mode")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(classes="home-root"):
            with Container(id="sidebar"):
                # Manteniamo la tua logica originale per il menu
                options = [f"{p.name} ({p.category})" for p in registry.all()]
                options.append("Esci")
                yield OptionList(*options, id="menu-list")
            with Container(id="main-content"):
                yield Static(HOME_MARKUP, id="home-title-view")
        yield Footer()

    def action_toggle_dark(self) -> None:
        app = self.app
        app.theme = "textual-dark" if app.theme == "textual-light" else "textual-light"

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        providers = registry.all()
        if event.option_index >= len(providers):
            self.app.exit()
            return

        self.app.push_screen(SearchScreen(providers[event.option_index]))
