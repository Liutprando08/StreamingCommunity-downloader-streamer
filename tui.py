from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, OptionList, Static, Header
from textual.widgets.option_list import Option
from textual.widget import Widget


class ColumnsContainer(Widget):
    DEFAULT_CSS = """
    ColumnsContainer {
        width: 1fr;
        height: 1fr;
        border: solid white;
    }
    """


class HomeScreen(Screen):
    BINDINGS = [("d", "toggle_dark", "Toggle dark mode")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        yield ColumnsContainer()

    def action_toggle_dark(self) -> None:
        app = self.app
        app.theme = "textual-dark" if app.theme == "textual-light" else "textual-light"


class OsteApp(App):
    def on_mount(self) -> None:
        self.push_screen(HomeScreen())


if __name__ == "__main__":
    OsteApp().run()
