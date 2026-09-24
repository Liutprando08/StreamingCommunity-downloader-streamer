from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList, Static

from ..providers import registry
from .search import SearchScreen

HOME_MARKUP = (
    "[b][magenta] ██████╗ ███████╗████████╗███████╗[/]\n"
    "[b][magenta]██╔═══██╗██╔════╝╚══██╔══╝██╔════╝[/]\n"
    "[b][magenta]██║   ██║███████╗   ██║   █████╗  [/]\n"
    "[b][magenta]██║   ██║╚════██║   ██║   ██╔══╝  [/]\n"
    "[b][magenta] ██████╔╝███████║   ██║   ███████╗[/]\n"
    "[b][magenta]  ╚════╝ ╚══════╝   ╚═╝   ╚══════╝[/]\n\n"
    "[i][dim]You are gonna be king of the pirates[/]"
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

    def on_mount(self) -> None:
        providers = registry.all()
        if len(providers) == 1:
            self.query_one("#home-title-view", Static).update(
                HOME_MARKUP + f"\n\n[cyan]Servizio attivo:[yellow] {providers[0].name}"
            )

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        prompt = str(event.option.prompt)
        if "Esci" in prompt:
            self.app.exit()
            return
        for provider in registry.all():
            if provider.name in prompt:
                self.app.push_screen(SearchScreen(provider))
                return
