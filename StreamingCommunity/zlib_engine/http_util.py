"""HTTP response classifiers shared by the client and the domain probe."""

from __future__ import annotations

import re
from email.message import Message

CHALLENGE_RE = re.compile(r"'([0-9A-Fa-f]{40})','c_token=")
DIAMWALL_TITLE_RE = re.compile(r"<title[^>]*>[^<]*diamwall[^<]*</title>", re.IGNORECASE | re.DOTALL)


def is_challenge_page(html: str) -> bool:
    return len(html) < 20000 and bool(CHALLENGE_RE.search(html))


def is_diamwall_status(status_code: int) -> bool:
    # 513: "Verifying your browser"; 517: "Access Denied".
    return status_code in {513, 517}


def is_html_body(content_type: str | None) -> bool:
    """Treat a missing type as HTML, but never scan declared JSON."""
    if not content_type:
        return True
    media_type = content_type.split(";", 1)[0].strip().lower()
    if not media_type:
        return True
    return media_type in {"text/html", "application/xhtml+xml"}


def is_bot_protection_response(status_code: int, headers, body: bytes) -> bool:
    if is_diamwall_status(status_code):
        return True
    content_type = ""
    if headers is not None:
        try:
            content_type = headers.get("Content-Type", "")
        except AttributeError:
            content_type = ""
        if isinstance(headers, Message):
            content_type = headers.get("Content-Type", "")
    if not is_html_body(content_type):
        return False
    return bool(DIAMWALL_TITLE_RE.search(body.decode("utf-8", errors="replace")))
