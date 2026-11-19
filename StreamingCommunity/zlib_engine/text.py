"""Text sanitising for untrusted server strings.

EAPI titles, author names and error messages end up on a terminal. Control
characters allow a hostile mirror to rewrite the screen or set the clipboard
(OSC 52), and Unicode bidi overrides can disguise a download filename. These
helpers mirror ``internal/zlib/text.go`` and ``internal/weread/client.go``.
"""

from __future__ import annotations

import json
import unicodedata
from typing import Any


def is_bidi_control(char: str) -> bool:
    code = ord(char)
    return (
        char in {"\u200e", "\u200f", "\u061c"}
        or 0x202A <= code <= 0x202E
        or 0x2066 <= code <= 0x2069
    )


def strip_control(value: str, keep: str = "\n\t") -> str:
    """Drop Unicode control (Cc) characters except those listed in *keep*."""
    return "".join(
        char for char in value if not (unicodedata.category(char) == "Cc" and char not in keep)
    )


def clean_text(value: str) -> str:
    """Strip control and bidi formatting characters, then trim whitespace."""
    cleaned = "".join(
        char
        for char in value
        if not (
            unicodedata.category(char) == "Cc"
            or is_bidi_control(char)
        )
        or char in {"\n", "\t"}
    )
    return cleaned.strip()


def clean_structure(value: Any) -> Any:
    """Recursively clean every string in parsed JSON.

    Mirrors Go's reflective ``cleanText``: dataclass-free dict/list structures
    are rebuilt so cleaned dictionary keys replace the originals.
    """
    if isinstance(value, str):
        return strip_control(value, "\n\t")
    if isinstance(value, list):
        return [clean_structure(item) for item in value]
    if isinstance(value, dict):
        return {clean_structure(key): clean_structure(item) for key, item in value.items()}
    return value


def loads_clean(body: bytes | str) -> Any:
    """Decode JSON and strip control characters from every string."""
    if isinstance(body, bytes):
        text = body.decode("utf-8", errors="replace")
    else:
        text = body
    return clean_structure(json.loads(text))


def _reject_constant(name: str) -> Any:
    raise ValueError(f"invalid JSON constant {name}")


def loads_strict(body: bytes | str) -> Any:
    """Like :func:`loads_clean` but rejects NaN and Infinity."""
    if isinstance(body, bytes):
        text = body.decode("utf-8", errors="replace")
    else:
        text = body
    return clean_structure(json.loads(text, parse_constant=_reject_constant))
