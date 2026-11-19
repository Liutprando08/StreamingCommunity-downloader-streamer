# 19.11.26 - Z-Library credential/session adapter.
#
# The vendored engine keeps its own session store under ~/.config/zlib. This
# module bridges it to the project conventions: credentials live in
# Conf/login.json, an existing engine session is reused when present, and a
# successful password login is persisted so the next run starts silently.

from __future__ import annotations

import json
import logging
import threading
from typing import Callable, TypeVar

# Engine
from StreamingCommunity.zlib_engine import (
    BotProtection,
    Client,
    Extension,
    Language,
    NoDomain,
    NotLoggedIn,
    Session,
    SessionExpired,
    TransportError,
    load_session,
    save_session,
)
from StreamingCommunity.zlib_engine.domain_probe import (
    EAPI_DOMAINS_INFO_PATH,
    DomainProbeOptions,
    DomainStatus,
    known_domains,
    probe_domains,
)
from StreamingCommunity.zlib_engine.model import SearchOptions
from StreamingCommunity.zlib_engine.urls import normalize_domain

# Internal utilities
from StreamingCommunity.utils import config_manager

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_client: Client | None = None
_client_key: tuple[str, str, int] = ("", "", 0)

# Last mirror that answered EAPI in this process. Mirrors churn and the
# configured one may be behind an anti-bot interstitial, so remember a working
# alternative until the process exits.
_resolved_domain = ""

T = TypeVar("T")

_MISSING_CREDENTIALS = (
    "Z-Library richiede un account. Compila Conf/login.json nella sezione "
    '"zlibrary" con "email" e "password" (oppure "remix_userid" e '
    '"remix_userkey" gia validi) e riprova.'
)


# ── configuration ───────────────────────────────────────────────────────────


def _config_str(key: str, default: str = "") -> str:
    return str(config_manager.config.get("ZLIBRARY", key, default=default) or "")


def configured_domain() -> str:
    """Mirror from Conf/domains.json, falling back to the engine default."""
    return normalize_domain(
        config_manager.domain.get("zlibrary", "full_url", default="")
    )


def configured_proxy() -> str:
    """Explicit Z-Library proxy, else the global proxy when it is enabled."""
    proxy = _config_str("proxy").strip()
    if proxy:
        return proxy
    if config_manager.config.get("REQUESTS", "use_proxy", bool, False):
        proxy_map = config_manager.config.get("REQUESTS", "proxy", dict, {})
        if isinstance(proxy_map, dict):
            return str(proxy_map.get("https") or proxy_map.get("http") or "").strip()
    return ""


def configured_retries() -> int:
    try:
        value = int(config_manager.config.get("ZLIBRARY", "download_retries", default=3))
    except (TypeError, ValueError):
        value = 3
    return max(1, value)


def configured_search_count() -> int:
    try:
        value = int(config_manager.config.get("ZLIBRARY", "search_count", default=20))
    except (TypeError, ValueError):
        value = 20
    return max(1, min(value, 50))


def search_options() -> SearchOptions:
    """Build engine search filters from the ZLIBRARY config section."""
    languages: list[str] = []
    language = _config_str("default_language").strip().lower()
    if language:
        languages.append(language)

    extensions: list[str] = []
    extension = _config_str("default_extension").strip().upper()
    if extension:
        extensions.append(extension)

    return SearchOptions(languages=languages, extensions=extensions)


def fetch_cover_enabled() -> bool:
    return bool(config_manager.config.get("ZLIBRARY", "fetch_cover", bool, False))


# ── credentials ─────────────────────────────────────────────────────────────


def _login_value(key: str) -> str:
    return str(config_manager.login.get("zlibrary", key, default="") or "").strip()


def configured_credentials() -> tuple[str, str, str, str]:
    """Return ``(email, password, remix_userid, remix_userkey)``."""
    return (
        _login_value("email"),
        _login_value("password"),
        _login_value("remix_userid"),
        _login_value("remix_userkey"),
    )


def has_configured_credentials() -> bool:
    email, password, user_id, user_key = configured_credentials()
    return bool((email and password) or (user_id and user_key))


def _stored_cookies() -> dict[str, str]:
    try:
        session = load_session()
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, json.JSONDecodeError):
        logger.debug("zlibrary: unreadable engine session, ignoring it", exc_info=True)
        return {}
    cookies = session.cookies
    if cookies.get("remix_userid") and cookies.get("remix_userkey"):
        return cookies
    return {}


def _persist_session(client: Client) -> None:
    try:
        save_session(
            Session(cookies=client.cookies(), domain=client.domain, mode="eapi")
        )
    except OSError:
        logger.debug("zlibrary: could not persist the engine session", exc_info=True)


def missing_credentials_message() -> str:
    return _MISSING_CREDENTIALS


# ── mirror selection ────────────────────────────────────────────────────────
#
# Z-Library serves different mirrors to different users and some of them sit
# behind a DiamWall interstitial that answers 513 to EAPI. The engine ships a
# read-only probe (no credentials) that classifies a mirror and checks whether
# ``/eapi/info/domains`` really returns JSON, which is a reliable "this mirror
# speaks EAPI" signal.


def _candidate_domains() -> list[str]:
    configured = configured_domain()
    ordered: list[str] = [configured] if configured else []
    for domain in known_domains():
        if domain not in ordered:
            ordered.append(domain)
    return ordered


def find_working_domain(exclude: set[str] | None = None) -> str:
    """Probe the known mirrors and return the first usable one.

    The configured domain is tried first so an explicit choice keeps winning.
    Results are cached for the rest of the process.
    """
    global _resolved_domain

    excluded = set(exclude or ())
    with _lock:
        if _resolved_domain and _resolved_domain not in excluded:
            return _resolved_domain

    candidates = [domain for domain in _candidate_domains() if domain not in excluded]
    if not candidates:
        raise NoDomain(
            "zlibrary: every known Z-Library mirror is blocked from this network"
        )

    checks = probe_domains(
        candidates,
        DomainProbeOptions(
            proxy_url=configured_proxy(), path=EAPI_DOMAINS_INFO_PATH
        ),
    )
    order = {domain: index for index, domain in enumerate(candidates)}
    usable = [
        check
        for check in checks
        if check.status == DomainStatus.HEALTHY and check.zlib_eapi
    ]
    usable.sort(key=lambda check: order.get(check.domain, len(order)))

    if not usable:
        raise NoDomain(
            "zlibrary: no reachable Z-Library mirror (all known domains are "
            "blocked or offline). Set ZLIBRARY.proxy or try again later."
        )

    domain = usable[0].domain
    with _lock:
        _resolved_domain = domain
    logger.info("zlibrary: using mirror %s", domain)
    return domain


def _switch_mirror(client: Client, *, exclude: set[str] | None = None) -> None:
    """Point ``client`` at another healthy mirror, keeping its session."""
    domain = find_working_domain(exclude=exclude)
    if domain != client.domain:
        client.set_domain(domain)
        logger.warning("zlibrary: switched mirror to %s", domain)


def run_with_mirror_retry(call: Callable[[Client], T]) -> T:
    """Run ``call`` and retry once on another mirror when it is blocked.

    Bot protection, dead mirrors and transport failures are all mirror-local:
    the same account and cookies work on another host. Anything else (auth,
    quota, parse errors) is propagated untouched.
    """
    client = get_client()
    try:
        return call(client)
    except (BotProtection, NoDomain, TransportError) as error:
        logger.warning("zlibrary: %s; probing another mirror", error)
        _switch_mirror(client, exclude={client.domain})
        return call(client)


# ── client lifecycle ────────────────────────────────────────────────────────


def _build_client() -> Client:
    return Client(
        domain=_resolved_domain or configured_domain() or None,
        proxy=configured_proxy() or None,
        download_retries=configured_retries(),
    )


def _ensure_login(client: Client) -> None:
    """Resolve an authenticated client: cookies → session file → password."""
    if client.is_logged_in:
        return

    email, password, user_id, user_key = configured_credentials()

    if user_id and user_key:
        client.set_cookies(
            {"remix_userid": user_id, "remix_userkey": user_key}
        )
        return

    cookies = _stored_cookies()
    if cookies:
        client.set_cookies(cookies)
        return

    if email and password:
        client.login(email, password)
        _persist_session(client)
        return

    raise NotLoggedIn(_MISSING_CREDENTIALS)


def get_client(*, force_new: bool = False) -> Client:
    """Return the shared authenticated client, creating it on first use."""
    global _client, _client_key

    key = (configured_domain(), configured_proxy(), configured_retries())
    with _lock:
        if _client is None or force_new or key != _client_key:
            _client = _build_client()
            _client_key = key
        try:
            _ensure_login(_client)
        except BotProtection as error:
            # Login itself can land on an anti-bot interstitial. Cookies and
            # credentials are mirror-independent, so retry on another host.
            logger.warning(
                "zlibrary: login blocked on %s (%s); probing another mirror",
                _client.domain,
                error,
            )
            _switch_mirror(_client, exclude={_client.domain})
            _ensure_login(_client)
        return _client


def reset_client() -> None:
    """Drop the cached client so the next call re-authenticates."""
    global _client, _client_key
    with _lock:
        _client = None
        _client_key = ("", "", 0)


def relogin(client: Client) -> Client:
    """Recover from an expired session with a single password login."""
    global _client, _client_key

    reset_client()
    email, password, _, _ = configured_credentials()
    if not (email and password):
        return get_client()
    with _lock:
        fresh = _build_client()
        fresh.login(email, password)
        _persist_session(fresh)
        _client = fresh
        _client_key = (
            configured_domain(),
            configured_proxy(),
            configured_retries(),
        )
        return fresh


__all__ = [
    "configured_domain",
    "configured_proxy",
    "configured_retries",
    "configured_search_count",
    "search_options",
    "fetch_cover_enabled",
    "configured_credentials",
    "has_configured_credentials",
    "missing_credentials_message",
    "find_working_domain",
    "run_with_mirror_retry",
    "get_client",
    "reset_client",
    "relogin",
    "SessionExpired",
    "Language",
    "Extension",
]
