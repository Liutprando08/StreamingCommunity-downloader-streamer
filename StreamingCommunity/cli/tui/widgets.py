# Shared TUI widgets.

from __future__ import annotations

from typing import Any, Iterable, cast

from textual.css.query import NoMatches, QueryType
from textual.message import Message
from textual.widgets import DataTable
from textual.widgets import Header as TextualHeader
from textual.widgets._header import HeaderTitle
from textual.widgets.data_table import RowKey

from .parse import parse_ranges


class _Detached:
    """No-op stand-in used once a Header's children are gone."""

    def update(self, *args: Any, **kwargs: Any) -> None:
        pass


class Header(TextualHeader):
    """Header that survives a title change racing screen teardown.

    ``Header._on_mount`` registers an async ``set_title`` watcher on the app
    and screen ``title`` reactives, which calls ``query_one(HeaderTitle)`` and
    guards only against ``NoScreen``. If the Header is mid-unmount and its
    children are already removed, the query raises ``NoMatches``, and
    ``MessagePump._flush_next_callbacks`` turns that into an app crash. The
    queue pops several screens from a single completion callback, which
    reliably hits that window.

    We cannot simply override ``_on_mount``: Textual's
    ``_get_dispatch_methods`` walks the whole MRO and yields the base class's
    ``_on_mount`` too, so the fragile handler still runs. Intercepting
    ``query_one`` covers both handlers.

    See ``textual/widgets/_header.py`` in the installed version.
    """

    def query_one(
        self,
        selector: str | type[QueryType],
        expect_type: type[QueryType] | None = None,
    ) -> QueryType:
        try:
            if isinstance(selector, str):
                node = (
                    super().query_one(selector)
                    if expect_type is None
                    else super().query_one(selector, expect_type)
                )
            else:
                node = super().query_one(selector)
        except NoMatches:
            is_header_title = selector is HeaderTitle or selector == "HeaderTitle"
            if not is_header_title:
                raise
            return _Detached()  # type: ignore[return-value]
        return cast("QueryType", node)


class SelectableTable(DataTable):
    """A ``DataTable`` with a leading toggle column and shared selection helpers.

    Seasons, episodes and tracks all need the same things: a "Sel" marker
    column, select-all/none, range parsing and a way to rebuild the rows from
    fresh data. Having it here means each screen only supplies its data columns
    and no longer re-implements (or mis-implements) the selection state.
    """

    class SelectionChanged(Message):
        """Posted whenever the set of selected row indices changes."""

        def __init__(self, table: "SelectableTable", selected: set[int]) -> None:
            self.table = table
            self.selected = set(selected)
            super().__init__()

        @property
        def control(self) -> "SelectableTable":
            # Lets ``@on(..., "#table-id")`` match on the posting table.
            return self.table

    def __init__(self, columns: Iterable[str] = (), **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._columns = list(columns)
        self._selected: set[int] = set()
        self._count = 0
        self._built = False
        self.cursor_type = "row"

    # ── columns / rows ────────────────────────────────────────────────────
    def ensure_columns(self) -> None:
        """Create the header row (idempotent)."""
        if not self._built:
            self._build_columns()

    def set_columns(self, columns: Iterable[str]) -> None:
        """Replace the data columns; clears rows and the current selection."""
        self._columns = list(columns)
        if self.is_mounted:
            self._build_columns()
            self._selected.clear()
            self._count = 0

    def _build_columns(self) -> None:
        # clear(columns=True) also drops the old column keys, so a rebuild can
        # never hit DataTable's DuplicateKey on the second fill.
        self.clear(columns=True)
        self.add_column("Sel", key="sel")
        for header in self._columns:
            self.add_column(header)
        self._built = True

    def set_rows(
        self, rows: Iterable[Iterable[Any]], selected: Iterable[int] | None = None
    ) -> None:
        """Replace every row. ``rows`` holds the data columns only (the marker
        is added automatically); ``selected`` optionally seeds the selection."""
        self.ensure_columns()
        self.clear()
        row_list = list(rows)
        self._count = len(row_list)
        self._selected = set(selected) if selected is not None else set()
        self._selected &= set(range(self._count))
        for index, row in enumerate(row_list):
            self.add_row(
                self._marker(index),
                *[str(cell) for cell in row],
                key=str(index),
            )
        self._emit()

    # ── selection API ─────────────────────────────────────────────────────
    @property
    def selected(self) -> set[int]:
        return set(self._selected)

    @property
    def count(self) -> int:
        return self._count

    def _marker(self, index: int) -> str:
        return "✓" if index in self._selected else " "

    def _emit(self) -> None:
        self.post_message(self.SelectionChanged(self, self._selected))

    def refresh_markers(self) -> None:
        for index in range(self._count):
            self.update_cell(RowKey(str(index)), "sel", self._marker(index))
        self._emit()

    def toggle(self, index: int) -> None:
        if not 0 <= index < self._count:
            return
        if index in self._selected:
            self._selected.discard(index)
        else:
            self._selected.add(index)
        self.update_cell(RowKey(str(index)), "sel", self._marker(index))
        self._emit()

    def select_all(self) -> None:
        self._selected = set(range(self._count))
        self.refresh_markers()

    def select_none(self) -> None:
        self._selected.clear()
        self.refresh_markers()

    def invert(self) -> None:
        self._selected = set(range(self._count)) - self._selected
        self.refresh_markers()

    def set_selected(self, indices: Iterable[int]) -> None:
        self._selected = {i for i in indices if 0 <= i < self._count}
        self.refresh_markers()

    def apply_range(self, text: str) -> None:
        """Add the 1-based numbers parsed from ``text`` to the selection."""
        for number in parse_ranges(text, max_count=self._count):
            self._selected.add(number - 1)
        self.refresh_markers()
