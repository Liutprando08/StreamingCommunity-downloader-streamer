"""Default domain resolution and URL helpers (mirrors ``internal/zlib/urls.go``)."""

from __future__ import annotations

import os

from .constants import DEFAULT_DOMAIN, ENV_DOMAIN

__all__ = [
    "DEFAULT_DOMAIN",
    "TOR_DOMAIN",
    "current_default_domain",
    "set_default_domain",
    "normalize_domain",
    "absolutize_url",
    "is_absolute_url",
]

from .constants import TOR_DOMAIN  # noqa: E402  (re-export)

_default_domain_override = ""


def normalize_domain(domain: str | None) -> str:
    return (domain or "").strip().rstrip("/")


def current_default_domain() -> str:
    """Resolve ``SetDefaultDomain > ZLIB_DOMAIN > DEFAULT_DOMAIN``.

    The environment is read on every call so a ``.env`` loaded after import is
    observed, matching the Go client.
    """
    if _default_domain_override:
        return _default_domain_override
    domain = normalize_domain(os.environ.get(ENV_DOMAIN))
    return domain or DEFAULT_DOMAIN


def set_default_domain(domain: str | None) -> None:
    global _default_domain_override
    _default_domain_override = normalize_domain(domain)


def is_absolute_url(raw_url: str) -> bool:
    return raw_url.startswith("http://") or raw_url.startswith("https://")


def absolutize_url(base: str, href: str) -> str:
    if not href:
        return ""
    if is_absolute_url(href):
        return href
    return base + href
