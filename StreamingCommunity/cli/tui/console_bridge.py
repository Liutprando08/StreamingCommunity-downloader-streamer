# Redirects Rich console output into an in-memory queue so it can be
# surfaced inside the Textual UI instead of corrupting the screen.

from __future__ import annotations

import io
import queue
import re

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_COLOR_TAG_RE = re.compile(r"\[/?[a-z_]+[^\]]*\]")


class QueueTextIO(io.TextIOBase):
    """A TextIO substitute that captures lines written by a Rich Console."""

    encoding = "utf-8"

    def __init__(self, q: "queue.Queue[str]"):
        super().__init__()
        self._q = q
        self._buf = ""

    def isatty(self) -> bool:
        return False

    def write(self, s) -> int:
        if isinstance(s, bytes):
            s = s.decode("utf-8", "replace")
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._push(line)
        return len(s)

    def flush(self) -> None:
        if self._buf:
            self._push(self._buf)
            self._buf = ""

    def _push(self, line: str) -> None:
        line = _ANSI_RE.sub("", line)
        line = _COLOR_TAG_RE.sub("", line).strip()
        if line:
            self._q.put(line)


class ConsoleBridge:
    """Allows the TUI to observe everything printed by the shared Rich console."""

    def __init__(self) -> None:
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._original_file = None
        self._installed = False

    def install(self) -> None:
        if self._installed:
            return
        from StreamingCommunity.utils.console.shared import console

        self._original_file = console.file
        try:
            console.file = QueueTextIO(self._queue)
            self._installed = True
        except Exception:
            console.file = self._original_file
            self._installed = False

    def restore(self) -> None:
        if not self._installed:
            return
        from StreamingCommunity.utils.console.shared import console

        try:
            if console.file is not None:
                console.file.flush()
        except Exception:
            pass
        console.file = self._original_file
        self._installed = False

    def drain(self, limit: int = 200) -> list[str]:
        lines: list[str] = []
        try:
            while True:
                lines.append(self._queue.get_nowait())
                if len(lines) >= limit:
                    break
        except queue.Empty:
            pass
        return lines


bridge = ConsoleBridge()