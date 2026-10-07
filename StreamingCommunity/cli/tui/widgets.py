# Shared TUI widgets.

from __future__ import annotations

from typing import Any, cast

from textual.css.query import NoMatches, QueryType
from textual.widgets import Header as TextualHeader
from textual.widgets._header import HeaderTitle


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
