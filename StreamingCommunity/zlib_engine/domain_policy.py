"""The Z-Library mirror allowlist and trusted user mirrors.

Mirrors churn, so the built-in list is maintained from measurement. User
mirrors are trusted as exact hosts, never as subdomains, because the login is
sent to them.
"""

from __future__ import annotations

import ipaddress
import re
import threading
import urllib.parse

from .errors import MirrorUnverified

ALLOWED_DOMAIN_SUFFIXES: tuple[str, ...] = (
    "1lib.sk",
    "article.sk",
    "articles.sk",
    "z-lib.by",
    "z-lib.fm",
    "z-lib.gd",
    "z-lib.gl",
    "z-lib.sk",
    "z-library.ec",
    "z-library.im",
    "z-library.qa",
    "z-library.sk",
    "z-library.website",
    "zlib.bz",
)

_user_mirrors_lock = threading.RLock()
_user_mirror_hosts: list[str] = []

_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


def allowed_domain_suffixes() -> list[str]:
    return list(ALLOWED_DOMAIN_SUFFIXES)


def _built_in_host(host: str) -> bool:
    return any(host == suffix or host.endswith("." + suffix) for suffix in ALLOWED_DOMAIN_SUFFIXES)


def _user_mirror_host(host: str) -> bool:
    with _user_mirrors_lock:
        return host in _user_mirror_hosts


def _split_origin(raw: str) -> urllib.parse.SplitResult:
    try:
        return urllib.parse.urlsplit(raw.strip())
    except ValueError as exc:
        raise ValueError("domain must be an HTTPS origin") from exc


def _port(parts: urllib.parse.SplitResult) -> int | None:
    try:
        return parts.port
    except ValueError as exc:
        raise ValueError("domain has an invalid port") from exc


def parse_allowed_domain(raw: str) -> str:
    """Validate an HTTPS origin and return it as ``https://host``."""
    parts = _split_origin(raw)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError("domain must be an HTTPS origin")
    if (
        parts.username is not None
        or parts.password is not None
        or _port(parts) is not None
        or parts.query
        or parts.fragment
        or parts.path not in {"", "/"}
    ):
        raise ValueError(
            "domain must be an HTTPS origin without credentials, port, path, query, or fragment"
        )
    host = parts.hostname.lower().rstrip(".")
    if _built_in_host(host) or _user_mirror_host(host):
        return "https://" + host
    raise ValueError(
        f'domain "{host}" is neither a built-in Z-Library domain nor one of your trusted mirrors'
    )


def parse_mirror_origin(raw: str) -> str:
    """Normalize a user mirror to ``https://host`` with strict validation."""
    value = (raw or "").strip()
    if not value:
        raise ValueError("enter a mirror domain such as mirror.example")
    if "://" not in value:
        value = "https://" + value
    parts = _split_origin(value)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError("a mirror must be an HTTPS domain")
    if (
        parts.username is not None
        or parts.password is not None
        or _port(parts) is not None
        or parts.query
        or parts.fragment
        or parts.path not in {"", "/"}
    ):
        raise ValueError(
            "a mirror must be a domain without credentials, port, path, query, or fragment"
        )
    host = parts.hostname.lower().rstrip(".")
    try:
        ipaddress.ip_address(host)
        is_ip = True
    except ValueError:
        is_ip = False
    if is_ip or "." not in host:
        raise ValueError(
            "a mirror must be a domain name such as mirror.example, not an IP address or a single-label host"
        )
    for label in host.split("."):
        if not _LABEL_RE.match(label):
            raise ValueError(
                f'"{host}" is not a valid domain name; use its punycode (xn--) form for non-ASCII names'
            )
    return "https://" + host


def is_built_in_domain(raw: str) -> bool:
    try:
        origin = parse_mirror_origin(raw)
    except ValueError:
        return False
    return _built_in_host(origin.removeprefix("https://"))


def set_user_mirrors(origins: list[str] | tuple[str, ...]) -> None:
    """Replace trusted mirrors; invalid entries are reported after valid ones apply."""
    hosts: list[str] = []
    errors: list[str] = []
    for raw in origins:
        try:
            origin = parse_mirror_origin(raw)
        except ValueError as exc:
            errors.append(f'mirror "{raw}": {exc}')
            continue
        host = origin.removeprefix("https://")
        if host not in hosts:
            hosts.append(host)
    with _user_mirrors_lock:
        _user_mirror_hosts[:] = hosts
    if errors:
        raise ValueError("; ".join(errors))


def user_mirrors() -> list[str]:
    with _user_mirrors_lock:
        return ["https://" + host for host in _user_mirror_hosts]


def verify_user_mirror(raw: str, options=None):
    """Probe a candidate mirror without credentials and judge its answer."""
    from .domain_probe import DomainProbeOptions, DomainStatus, EAPI_DOMAINS_INFO_PATH, probe_domain_with_options

    origin = parse_mirror_origin(raw)
    if options is None:
        options = DomainProbeOptions()
    options = DomainProbeOptions(proxy_url=options.proxy_url, path=EAPI_DOMAINS_INFO_PATH)
    check = probe_domain_with_options(origin, options)
    if check.status != DomainStatus.HEALTHY:
        detail = str(check.status)
        if check.detail:
            detail += ": " + check.detail
        raise MirrorUnverified(f"zlibrary: mirror did not answer as Z-Library: {origin} ({detail})")
    final = urllib.parse.urlsplit(check.final_url)
    expected = origin.removeprefix("https://")
    if final.scheme != "https" or (final.hostname or "").lower() != expected:
        raise MirrorUnverified(
            f"zlibrary: mirror did not answer as Z-Library: {origin} redirects to "
            f"{check.final_url}; add the domain it redirects to instead"
        )
    if not check.zlib_eapi:
        raise MirrorUnverified(
            f"zlibrary: mirror did not answer as Z-Library: {origin} answered, but not with the Z-Library EAPI"
        )
    return check


__all__ = [
    "ALLOWED_DOMAIN_SUFFIXES",
    "allowed_domain_suffixes",
    "parse_allowed_domain",
    "parse_mirror_origin",
    "is_built_in_domain",
    "set_user_mirrors",
    "user_mirrors",
    "verify_user_mirror",
]
