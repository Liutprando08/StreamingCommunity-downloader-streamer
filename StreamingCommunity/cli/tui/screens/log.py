# Log widget bound to the ConsoleBridge so console output becomes visible
# inside the TUI instead of being written over the screen.

from __future__ import annotations

from textual.widgets import Log

from ..console_bridge import bridge


class LogPanel(Log):
    """A Textual Log that periodically absorbs captured console lines."""

    def drain_console(self, max_lines: int = 200) -> None:
        lines = bridge.drain(max_lines)
        if lines:
            self.write_lines(lines)