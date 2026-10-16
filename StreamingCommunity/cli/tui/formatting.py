# Small, pure rendering helpers shared by the TUI screens.

from __future__ import annotations

import datetime
from collections.abc import Iterable
from typing import Any


def format_time(timestamp: Any) -> str:
    """Render a unix timestamp as local ``YYYY-MM-DD HH:MM:SS``.

    Non-numeric values are stringified and falsy ones become ``-``.
    """
    if not timestamp:
        return "-"
    if isinstance(timestamp, (int, float)):
        try:
            return datetime.datetime.fromtimestamp(timestamp).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except (ValueError, OSError, OverflowError):
            return str(timestamp)
    return str(timestamp)


def progress_bar(percentage: Any, width: int = 10) -> str:
    """Render a block progress bar such as ``██████░░░░  60.0%``.

    Any value that is not a number is treated as 0%, making the helper safe to
    call on half-populated tracker entries.
    """
    try:
        value = max(0.0, min(100.0, float(percentage)))
    except (TypeError, ValueError):
        value = 0.0
    filled = int(width * value / 100.0)
    bar = "█" * filled + "░" * (width - filled)
    return f"{bar} {value:5.1f}%"


def status_badge(status: Any) -> str:
    """Map a raw download status to a short coloured badge.

    Tracker statuses are loose strings ("downloading", "starting",
    "cancelling...", "timed_out", ...), so the matching is intentionally
    tolerant rather than an exact lookup.
    """
    text = str(status or "").strip().lower()
    if "cancel" in text:
        return "[bold #f9e2af]⏸ annullato[/]"
    if any(word in text for word in ("run", "down", "start", "active", "merg")):
        return "[bold #89dceb]● in corso[/]"
    if any(word in text for word in ("timeout", "timed_out", "expir")):
        return "[bold #f38ba8]⏱ scaduto[/]"
    if any(word in text for word in ("fail", "error", "err")):
        return "[bold #f38ba8]✖ errore[/]"
    if any(word in text for word in ("complet", "done", "finish", "success")):
        return "[bold #a6e3a1]✓ completato[/]"
    return f"[dim]· {status or 'sconosciuto'}[/dim]"


def escape_markup(text: Any) -> str:
    """Escape ``[`` so arbitrary entry text is rendered literally.

    Descriptions, URLs and titles can contain square brackets that Textual
    would otherwise parse as console markup tags.
    """
    return str(text).replace("[", r"\[")


def detail_lines(pairs: Iterable[tuple[Any, Any]]) -> list[str]:
    """Render ``(label, value)`` pairs as aligned ``label  value`` markup lines.

    Blank/``None`` values are dropped so callers can hand over raw entry
    attributes without pre-filtering them. Values are markup-escaped. Returns
    ``[]`` when nothing is left, letting callers hide the whole block.
    """
    cleaned: list[tuple[str, str]] = []
    for label, value in pairs:
        text = "" if value is None else str(value).strip()
        if text:
            cleaned.append((str(label), text))
    if not cleaned:
        return []
    width = max(len(label) for label, _ in cleaned)
    return [
        f"[dim]{label:<{width}}[/]  [#cdd6f4]{escape_markup(text)}[/]"
        for label, text in cleaned
    ]


def format_number(value: Any) -> str:
    """Render an episode/volume identifier without a spurious ``.0``.

    Sources may expose numbers as floats (manga volumes, half chapters, ...),
    so ``1.0`` becomes ``"1"`` while ``1.5`` stays ``"1.5"``. Falsy values
    become ``""`` and anything non-numeric is stringified.
    """
    if not value:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return str(number)


def media_badge(provider: Any, is_series: bool) -> tuple[str, str]:
    """Return the ``(icon, label)`` badge for an entry.

    Providers may override the generic "Serie"/"Film" badge through the
    ``series_icon``/``series_label`` (and ``film_*``) attributes so specialised
    catalogs read correctly, e.g. MangaWorld renders "📚 Manga".
    """
    if is_series:
        return (
            getattr(provider, "series_icon", "📺"),
            getattr(provider, "series_label", "Serie"),
        )
    return (
        getattr(provider, "film_icon", "🎬"),
        getattr(provider, "film_label", "Film"),
    )


def preview_card(
    title: Any,
    badges: str = "",
    details: Iterable[tuple[Any, Any]] = (),
    footer: str = "",
) -> str:
    """Render a side-panel "preview" card as a single markup string.

    Shared by the search results preview and by the seasons/episodes selection
    cards so they all read the same: bold title, a badge line, an aligned
    ``Dettagli`` block and an optional footer (e.g. a selection counter).
    Empty parts are omitted.
    """
    lines = [f"[bold #cdd6f4]{escape_markup(title)}[/]"]
    if badges:
        lines.append(badges)
    block = detail_lines(details)
    if block:
        lines.append("")
        lines.append("[bold #89dceb]Dettagli[/]")
        lines.extend(block)
    if footer:
        lines.append("")
        lines.append(footer)
    return "\n".join(lines)


# Friendly labels for entry attributes that are not already covered by a
# provider's ``result_columns()`` headers.
_INFO_LABELS = {
    "name": "Nome",
    "title": "Titolo",
    "type": "Tipo",
    "year": "Anno",
    "desc": "Trama",
    "description": "Descrizione",
    "overview": "Trama",
    "id": "ID interno",
    "url": "URL",
    "size": "Dimensione",
    "score": "Punteggio",
    "slug": "Slug",
    "quality": "Qualità",
    "seeders": "Seeders",
    "source": "Fonte",
    "provider_language": "Lingua",
    "tmdb_id": "TMDB",
    "imdb_id": "IMDB",
    "image": "Immagine",
    "poster": "Poster",
    "duration": "Durata",
    "artist": "Artista",
    "album": "Album",
    "category": "Categoria",
    "channel": "Canale",
    "number": "Numero",
    "video_id": "Video ID",
    "main_guid": "GUID",
    "path_id": "Path ID",
}


def entry_info(
    entry: Any, columns: Iterable[tuple[str, str]] = (), exclude: Iterable[str] = ()
) -> list[tuple[str, str]]:
    """Collect every meaningful text field of ``entry`` for the detail card.

    Provider-declared ``columns`` are listed first with their friendly
    headers; every remaining public attribute of the entry follows, using a
    friendly label when one is known. Private attributes, callables, names in
    ``exclude`` and names already covered by a column are skipped.
    """
    seen: set[str] = {str(name) for name in exclude}
    pairs: list[tuple[str, str]] = []

    for header, attr in columns:
        if attr in seen:
            continue
        seen.add(attr)
        pairs.append((str(header), getattr(entry, attr, "")))

    try:
        attributes = dict(vars(entry))
    except TypeError:
        attributes = {}

    for key, value in attributes.items():
        if key.startswith("_") or key in seen or callable(value):
            continue
        seen.add(key)
        pairs.append(
            (_INFO_LABELS.get(key, key.replace("_", " ").capitalize()), value)
        )

    return pairs


