# OSTE — Textual TUI entry point.

from __future__ import annotations

from textual.app import App

from .console_bridge import bridge
from .screens.home import HomeScreen


class OsteApp(App):
    TITLE = "OSTE"
    SUB_TITLE = "you are gonna be king of the pirates"

    CSS = """
    Screen {
        background: #12111a;
    }

    HomeScreen .home-root {
        width: 1fr;
        height: 1fr;
        border: solid white;
        layout:   horizontal;
        content-align: center middle;
    }

    HomeScreen #sidebar {
        width: 34;
        height: 100%;
        border-right: solid gray;
    }

    HomeScreen #sidebar OptionList {
        height: 1fr;
        border: none;
    }

    HomeScreen #main-content {
        width: 1fr;
        height: 100%;
        }
  
  #home-title-view {
        width: 1fr;
        height: 1fr;  
        content-align: center middle;
    }

    .flow-root {
        height: 1fr;
        padding: 1 2;
    }

    .flow-root #table-box {
        height: 1fr;
        border: round $accent;
        padding: 1;
    }

    .flow-root #table-box DataTable {
        height: 1fr;
    }

    .flow-root #queue-log {
        height: 6;
        border: round $primary;
        margin-top: 1;
    }

    .flow-root Horizontal {
        height: auto;
        margin: 1 0;
    }

    .flow-root Horizontal Input {
        width: 1fr;
        margin-right: 1;
    }
    """

    def on_mount(self) -> None:
        from StreamingCommunity.utils import config_manager

        config_manager.config.set_key("DEFAULT", "show_message", False)
        from StreamingCommunity.source.utils.tracker import context_tracker

        context_tracker.is_gui = True
        bridge.install()

        self.push_screen(HomeScreen())

    def on_unmount(self) -> None:
        bridge.restore()


def run() -> None:
    OsteApp().run()
