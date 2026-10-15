# OSTE — Textual TUI entry point.

from __future__ import annotations

from textual.app import App
from rich.terminal_theme import TerminalTheme

from .console_bridge import bridge
from .screens.home import HomeScreen

# ANSI → 24-bit mapping used by Textual's line filters. Markup strings in the
# screens carry explicit Catppuccin hexes (Textual resolves named markup colours
# like ``[cyan]`` to their raw ANSI RGB values, bypassing this mapping); this
# theme is the fallback for any colour that still reaches the terminal as an
# ANSI index, keeping those in Catppuccin Mocha tones as well.
_CATPPUCCIN_ANSI = TerminalTheme(
    background=(24, 24, 37),  # mantle    #181825
    foreground=(205, 214, 244),  # text    #cdd6f4
    normal=[
        (17, 17, 27),  # black          #11111b
        (243, 139, 168),  # red         #f38ba8
        (166, 227, 161),  # green       #a6e3a1
        (249, 226, 175),  # yellow      #f9e2af
        (137, 180, 250),  # blue        #89b4fa
        (203, 166, 247),  # magenta     #cba6f7
        (137, 220, 235),  # cyan        #89dceb
        (205, 214, 244),  # white       #cdd6f4
    ],
    bright=[
        (88, 91, 112),  # bright black  #585b70
        (243, 139, 168),  # bright red
        (166, 227, 161),  # bright green
        (249, 226, 175),  # bright yellow
        (137, 180, 250),  # bright blue
        (203, 166, 247),  # bright magenta
        (137, 220, 235),  # bright cyan
        (230, 233, 239),  # bright white #e6e9ef
    ],
)


class OsteApp(App):
    TITLE = "OSTE"
    SUB_TITLE = "you are gonna be king of the pirates"

    # All styling lives in the external stylesheet next to this module.
    CSS_PATH = "theme.tcss"

    # Global: works from any screen and, unlike a letter, is not swallowed by
    # the focused Input on the home screen.
    BINDINGS = [("f2", "open_settings", "Impostazioni")]

    def on_mount(self) -> None:
        from StreamingCommunity.utils import config_manager

        # Built-in Catppuccin Mocha theme for all widgets (buttons, inputs,
        # footer, focus…) plus the matching ANSI mapping for text markup.
        self.theme = "catppuccin-mocha"
        self.ansi_theme_dark = _CATPPUCCIN_ANSI

        config_manager.config.set_key("DEFAULT", "show_message", False)
        from StreamingCommunity.source.utils.tracker import context_tracker

        context_tracker.is_gui = True
        bridge.install()

        self.push_screen(HomeScreen())

    def on_unmount(self) -> None:
        bridge.restore()

    def action_open_settings(self) -> None:
        from .screens.settings import SettingsScreen

        self.push_screen(SettingsScreen())


def run() -> None:
    OsteApp().run()
