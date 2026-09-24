# Selection parsing helpers mirroring the CLI logic used by the base
# tv_display_manager (manage_selection), but without terminal-exit/reprompt,
# so it is safe to reuse inside the TUI.

from __future__ import annotations


def parse_ranges(cmd: str | None, max_count: int | None = None) -> list[int]:
    """Parse a selection command like ``1,3-5,*`` into sorted unique integers.

    Supported syntax:
        - single numbers: ``1``, ``2``
        - comma separated: ``1,3,5``
        - ranges: ``2-6``
        - open ended ranges: ``2-`` or ``2-*`` (up to ``max_count``)
        - everything: ``*`` (1..max_count)

    Returns an empty list for empty/invalid/quit input.
    """
    if cmd is None:
        return []

    text = str(cmd).strip()
    if not text or text.lower() in ("q", "quit"):
        return []

    selection: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue

        if part == "*":
            if max_count is not None:
                selection.extend(range(1, max_count + 1))
            continue

        if "-" in part:
            start_s, end_s = (x.strip() for x in part.split("-", 1))
            try:
                start = int(start_s)
            except ValueError:
                continue

            if end_s in ("", "*"):
                end = max_count if max_count is not None else start
            else:
                try:
                    end = int(end_s)
                except ValueError:
                    continue

            if max_count is not None:
                end = min(end, max_count)
            if end >= start:
                selection.extend(range(start, end + 1))
            continue

        try:
            n = int(part)
        except ValueError:
            continue
        if max_count is not None and not 1 <= n <= max_count:
            continue
        selection.append(n)

    return sorted(set(selection))