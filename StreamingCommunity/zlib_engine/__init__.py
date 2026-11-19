"""The zlib engine in Python.

A stdlib-only port of the Go core under ``internal/zlib``, ``internal/config``
and ``internal/weread``: Z-Library EAPI login/search/book details, downloads,
cover validation, mirror policy and probing, Send-to-Kindle SMTP, and WeRead
imports.

Example::

    from StreamingCommunity.zlib_engine import Client, SearchOptions, Language

    client = Client()
    client.login("you@example.com", "password")
    result = client.search("dune", options=SearchOptions(languages=[Language.ENGLISH]))
    client.download(result.books[0].download_url, "./books")

The module never starts a TUI. It is the engine layer a CLI, service or agent
can build on.
"""

from __future__ import annotations

from .client import Client, ClientMode
from .config import (
    Config,
    Session,
    config_dir,
    load_config,
    load_kindle,
    load_session,
    load_weread,
    save_config,
    save_kindle,
    save_session,
    save_weread,
)
from .constants import Extension, Language, OrderOption
from .cover import Cover, decode_cover
from .domain_policy import (
    allowed_domain_suffixes,
    is_built_in_domain,
    parse_allowed_domain,
    parse_mirror_origin,
    set_user_mirrors,
    user_mirrors,
    verify_user_mirror,
)
from .domain_probe import (
    DomainCheck,
    DomainProbeOptions,
    DomainStatus,
    known_domains,
    probe_domain,
    probe_domains,
    probe_domains_each,
)
from .download import clean_filename, sanitize_filename
from .errors import (
    BotProtection,
    BotProtectionError,
    Cancelled,
    ChallengeFailed,
    DownloadFailed,
    EmptyQuery,
    HTTPStatusError,
    InvalidProxy,
    LoginFailed,
    MirrorUnverified,
    NoDomain,
    NoID,
    NotLoggedIn,
    ParseFailed,
    PhraseMinWords,
    RedirectLoop,
    SMTPSend,
    SessionExpired,
    TransportError,
    Unsupported,
    ZlibError,
)
from .kindle import KindleConfig, send_to_kindle
from .model import (
    Book,
    DownloadHistoryItem,
    DownloadHistoryResult,
    DownloadLimit,
    DownloadResult,
    SearchOptions,
    SearchResult,
    UserProfile,
)
from .urls import current_default_domain, set_default_domain
from . import weread

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "Client",
    "ClientMode",
    "Book",
    "SearchOptions",
    "SearchResult",
    "DownloadLimit",
    "DownloadResult",
    "DownloadHistoryItem",
    "DownloadHistoryResult",
    "UserProfile",
    "Extension",
    "Language",
    "OrderOption",
    "Cover",
    "decode_cover",
    "KindleConfig",
    "send_to_kindle",
    "Config",
    "Session",
    "config_dir",
    "load_config",
    "save_config",
    "load_session",
    "save_session",
    "load_kindle",
    "save_kindle",
    "load_weread",
    "save_weread",
    "allowed_domain_suffixes",
    "parse_allowed_domain",
    "parse_mirror_origin",
    "is_built_in_domain",
    "set_user_mirrors",
    "user_mirrors",
    "verify_user_mirror",
    "DomainStatus",
    "DomainCheck",
    "DomainProbeOptions",
    "known_domains",
    "probe_domain",
    "probe_domains",
    "probe_domains_each",
    "clean_filename",
    "sanitize_filename",
    "current_default_domain",
    "set_default_domain",
    "weread",
    "ZlibError",
    "LoginFailed",
    "NotLoggedIn",
    "NoDomain",
    "EmptyQuery",
    "NoID",
    "InvalidProxy",
    "ParseFailed",
    "SessionExpired",
    "PhraseMinWords",
    "Unsupported",
    "DownloadFailed",
    "SMTPSend",
    "BotProtection",
    "BotProtectionError",
    "RedirectLoop",
    "ChallengeFailed",
    "MirrorUnverified",
    "Cancelled",
    "TransportError",
    "HTTPStatusError",
]
