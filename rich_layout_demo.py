"""
AURORA — home menu interattivo per terminale, costruito con Textual.

Textual renderizza un unico frame aggiornato con diff sullo schermo:
niente clear+print a ogni tasto, quindi nessuno sfarfallio.

Esegui con:  python rich_layout_demo.py
"""

import random
import time

from rich.color import ColorTriplet, blend_rgb
from rich.text import Text

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Label, OptionList, ProgressBar, Static, Switch, Tree
from textual.widgets.option_list import Option

# ---------------------------------------------------------------------------
# Font a blocchi per il titolo grande (6 righe × 5 colonne per lettera)
# ---------------------------------------------------------------------------

FONT = {
    "A": (".███.", "██.██", "█...█", "█████", "█...█", "█...█"),
    "B": ("████.", "█...█", "████.", "█...█", "█...█", "████."),
    "C": (".████", "█....", "█....", "█....", "█....", ".████"),
    "D": ("████.", "█...█", "█...█", "█...█", "█...█", "████."),
    "E": ("█████", "█....", "████.", "█....", "█....", "█████"),
    "F": ("█████", "█....", "████.", "█....", "█....", "█...."),
    "G": (".████", "█....", "█.███", "█...█", "█...█", ".███."),
    "H": ("█...█", "█...█", "█████", "█...█", "█...█", "█...█"),
    "I": ("█████", "..█..", "..█..", "..█..", "..█..", "█████"),
    "J": ("..███", "...█.", "...█.", "...█.", "█..█.", ".██.."),
    "K": ("█...█", "█..█.", "███..", "█..█.", "█...█", "█...█"),
    "L": ("█....", "█....", "█....", "█....", "█....", "█████"),
    "M": ("█...█", "██.██", "█.█.█", "█...█", "█...█", "█...█"),
    "N": ("█...█", "██..█", "██..█", "█.█.█", "█..██", "█..██"),
    "O": (".███.", "█...█", "█...█", "█...█", "█...█", ".███."),
    "P": ("████.", "█...█", "█...█", "████.", "█....", "█...."),
    "Q": (".███.", "█...█", "█...█", "█.█.█", "█..█.", ".██.█"),
    "R": ("████.", "█...█", "█...█", "████.", "█..█.", "█...█"),
    "S": (".████", "█....", ".███.", "....█", "....█", "████."),
    "T": ("█████", "..█..", "..█..", "..█..", "..█..", "..█.."),
    "U": ("█...█", "█...█", "█...█", "█...█", "█...█", ".███."),
    "V": ("█...█", "█...█", "█...█", "█...█", ".█.█.", "..█.."),
    "W": ("█...█", "█...█", "█...█", "█.█.█", "██.██", "█...█"),
    "X": ("█...█", ".█.█.", "..█..", "..█..", ".█.█.", "█...█"),
    "Y": ("█...█", ".█.█.", "..█..", "..█..", "..█..", "..█.."),
    "Z": ("█████", "...█.", "..█..", ".█...", "█....", "█████"),
    " ": (".....", ".....", ".....", ".....", ".....", "....."),
    ".": (".....", ".....", ".....", ".....", ".....", "..█.."),
    "!": ("..█..", "..█..", "..█..", "..█..", ".....", "..█.."),
    "?": (".███.", "█...█", "...██", "..█..", ".....", "..█.."),
}

FALLBACK = ("█████", "█...█", "█...█", "█...█", "█...█", "█████")


def title_text(
    title: str, start: tuple[int, int, int], end: tuple[int, int, int]
) -> Text:
    """Titolo grande come oggetto rich.Text, con gradient per lettera."""
    chars = [ch.upper() for ch in title]
    lines = [Text() for _ in range(6)]
    total = max(1, len(chars) - 1)
    c1, c2 = ColorTriplet(*start), ColorTriplet(*end)
    for i, ch in enumerate(chars):
        col = blend_rgb(c1, c2, i / total).hex
        glyph = FONT.get(ch, FALLBACK)
        for r in range(6):
            row = glyph[r].replace(".", " ")
            lines[r].append(row, style=f"bold {col}")
            if i < len(chars) - 1:
                lines[r].append(" ")
    result = Text()
    for r, line in enumerate(lines):
        result.append_text(line)
        if r < 5:
            result.append("\n")
    return result


# ---------------------------------------------------------------------------
# Stato condiviso tra schermate
# ---------------------------------------------------------------------------

class State:
    temp = 21
    beep = True
    anim = True
    compact = False
    party = False


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

CSS = """
HomeScreen, SystemScreen, ThermoScreen, FilesScreen, SettingsScreen, InfoScreen {
    align: center middle;
}

#bigtitle {
    height: auto;
    text-align: center;
    margin: 0 2 1 2;
}

#subtitle {
    color: $text-muted;
    text-align: center;
    margin-bottom: 1;
}

#menu {
    width: 76%;
    max-width: 92;
}

OptionList {
    height: auto;
    border: round $primary;
    background: $surface;
    padding: 1 2;
}

OptionList:focus {
    border: round $secondary;
}

#hint {
    color: $text-muted;
    text-align: center;
    margin-top: 1;
}

#title {
    text-align: center;
    width: 100%;
}
"""


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------

class HomeScreen(Screen):
    BINDINGS = [
        Binding("q", "quit", "Esci"),
        Binding("escape", "quit", "Esci"),
    ]

    def compose(self) -> ComposeResult:
        yield Static(title_text("AURORA", (95, 170, 255), (255, 120, 220)), id="bigtitle")
        yield Static("interactive terminal menu", id="subtitle")
        yield OptionList(
            Option("[bold cyan]📊  Sistema[/]", "system"),
            Option("[bold red]🌡  Termometro[/]", "thermo"),
            Option("[bold yellow]📁  Cartelle[/]", "files"),
            Option("[bold magenta]⚙  Impostazioni[/]", "settings"),
            Option("[bold blue]📖  Info[/]", "info"),
            Option("[bold red]✕  Esci[/]", "quit"),
            id="menu",
        )
        yield Static("↑↓ muovi · invio seleziona · Q esce", id="hint")

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()
        self.query_one(OptionList).highlighted = 0

    def action_quit(self) -> None:
        self.app.exit()

    @on(OptionList.OptionSelected)
    def _selected(self, event: OptionList.OptionSelected) -> None:
        target = event.option_id
        if target == "quit":
            self.app.exit()
        elif target == "system":
            self.app.push_screen(SystemScreen())
        elif target == "thermo":
            self.app.push_screen(ThermoScreen())
        elif target == "files":
            self.app.push_screen(FilesScreen())
        elif target == "settings":
            self.app.push_screen(SettingsScreen())
        elif target == "info":
            self.app.push_screen(InfoScreen())


# ---------------------------------------------------------------------------
# Sistema (dashboard con barre live)
# ---------------------------------------------------------------------------

SYSTEM_GREP = (("cpu_bar", "CPU", "cyan"), ("ram_bar", "RAM", "magenta"),
               ("net_bar", "NET", "green"), ("disk_bar", "DISK", "yellow"))


class SystemScreen(Screen):
    BINDINGS = [
        Binding("q", "back", "Menu"),
        Binding("escape", "back", "Menu"),
    ]

    def compose(self) -> ComposeResult:
        yield Static("SISTEMA · monitor risorse (live)", id="title")
        for w_id, name, color in SYSTEM_GREP:
            with Horizontal():
                yield Label(f"[bold {color}]{name}[/]")
                yield ProgressBar(show_eta=False, id=w_id)
        yield Static("", id="syslog")
        yield Static("Q per tornare al menu", id="hint")

    def on_mount(self) -> None:
        self.set_interval(0.4, self._tick)
        self._tick()

    def action_back(self) -> None:
        self.app.pop_screen()

    def _tick(self) -> None:
        for w_id, _, _ in SYSTEM_GREP:
            bar = self.query_one(f"#{w_id}", ProgressBar)
            bar.total = 100
            bar.progress = random.uniform(10, 92)
        self.query_one("#syslog", Static).update(
            f"[dim]{time.strftime('%H:%M:%S')}[/] [green]OK[/] caricamento bilanciato · "
            f"modalità T={State.temp}° · finestre 42×1×1"
        )


# ---------------------------------------------------------------------------
# Termometro (regolabile con frecce ← →)
# ---------------------------------------------------------------------------

class ThermoScreen(Screen):
    BINDINGS = [
        Binding("left", "dec", "più freddo", show=False),
        Binding("right", "inc", "più caldo", show=False),
        Binding("enter", "back", "Ok"),
        Binding("q", "back", "Menu"),
        Binding("escape", "back", "Menu"),
    ]

    def compose(self) -> ComposeResult:
        yield Static("TERMOMETRO · frecce ← → per regolare", id="title")
        yield Static("", id="thermo_bar", classes="big")
        yield Static("", id="thermo_status", classes="big")
        yield Static("invio / Q per confermare", id="hint")

    def on_mount(self) -> None:
        self.refresh_bar()

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_inc(self) -> None:
        if State.temp < 100:
            State.temp += 1
        self.refresh_bar()

    def action_dec(self) -> None:
        if State.temp > 0:
            State.temp -= 1
        self.refresh_bar()

    def refresh_bar(self) -> None:
        t = State.temp
        color = "cyan" if t < 20 else "green" if t < 45 else "yellow" if t < 70 else "red"
        filled = int(round(t))
        bar = "█" * (filled * 4 // 10) + "░" * ((100 - t) * 4 // 10)
        status = (
            "[cyan]Freddo ❄[/]" if t < 15
            else "[green]Perfetto ☀[/]" if t < 30
            else "[green]Tiepido[/]" if t < 45
            else "[yellow]Caldo 🔥[/]" if t < 70
            else "[red]BOLLENTE ☠[/]"
        )
        self.query_one("#thermo_bar", Static).update(f"[bold {color}]{bar} {t:3d}°C[/]")
        self.query_one("#thermo_status", Static).update(status)


# ---------------------------------------------------------------------------
# Cartelle (albero di directory)
# ---------------------------------------------------------------------------

class FilesScreen(Screen):
    BINDINGS = [
        Binding("q", "back", "Menu"),
        Binding("escape", "back", "Menu"),
    ]

    def compose(self) -> ComposeResult:
        yield Static("STRUTTURA PROGETTI", id="title")
        with Vertical(id="treewrap"):
            yield Tree("AItest", id="filetree")
        yield Static("Q per tornare al menu", id="hint")

    def on_mount(self) -> None:
        tree = self.query_one("#filetree", Tree)
        src = tree.root.add("src")
        src.add("…")
        docs = tree.root.add("docs")
        docs.add_leaf("[dim]manuale.txt[/] · 4.2 KB")
        doc = docs.add("foglio.py · 8.1 KB")
        doc.add_leaf("[green]✔ compilato[/]")
        assets = tree.root.add("assets")
        assets.add("…")
        tree.root.expand()
        docs.expand()
        tree.focus()

    def action_back(self) -> None:
        self.app.pop_screen()


# ---------------------------------------------------------------------------
# Impostazioni (interruttori)
# ---------------------------------------------------------------------------

SWITCHES = [
    ("beep", "Suono al risveglio"),
    ("anim", "Animazioni fluide"),
    ("compact", "Modalità compatta"),
    ("party", "Modalità festa"),
]


class SettingsScreen(Screen):
    BINDINGS = [
        Binding("q", "back", "Menu"),
        Binding("escape", "back", "Menu"),
    ]

    def compose(self) -> ComposeResult:
        yield Static("IMPOSTAZIONI · Tab/spazio · invio alterna · Q esci", id="title")
        for key, label in SWITCHES:
            with Horizontal(id=f"row_{key}"):
                yield Switch(getattr(State, key), id=key)
                yield Label(f"[bold]{label}[/]")
        yield Static("Temperatura salvata: [b]%d°C[/]" % State.temp, id="hint")

    def on_mount(self) -> None:
        self.query_one("#beep", Switch).focus()

    def action_back(self) -> None:
        self.app.pop_screen()

    @on(Switch.Changed)
    def _changed(self, event: Switch.Changed) -> None:
        key = event.switch.id or ""
        if key in (name for name, _ in SWITCHES):
            setattr(State, key, event.value)


# ---------------------------------------------------------------------------
# Info
# ---------------------------------------------------------------------------

class InfoScreen(Screen):
    BINDINGS = [
        Binding("q", "back", "Menu"),
        Binding("escape", "back", "Menu"),
    ]

    def compose(self) -> ComposeResult:
        yield Static(
            "[b]AURORA[/] — home menu interattivo con [bold cyan]Textual[/].\n\n"
            "[b]Tasti:[/]\n"
            "  [cyan]↑ ↓[/]      muovi nel menu\n"
            "  [cyan]← →[/]      regola il termometro\n"
            "  [cyan]spazio[/]   attiva gli interruttori\n"
            "  [cyan]invio[/]    conferma\n"
            "  [cyan]Q / Esc[/]  torna al menu o esci\n\n"
            "[dim]100% offline. Solo terminale e rich. ✨[/]",
            id="info_panel",
        )
        yield Static("Q per tornare al menu", id="hint")

    def action_back(self) -> None:
        self.app.pop_screen()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class AuroraApp(App):
    TITLE = "AURORA"
    SUB_TITLE = "interactive terminal menu"
    CSS = CSS

    def compose(self) -> ComposeResult:
        yield Footer()

    def on_mount(self) -> None:
        self.push_screen(HomeScreen())


if __name__ == "__main__":
    AuroraApp().run()