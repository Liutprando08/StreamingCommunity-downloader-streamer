# Central logging configuration.
#
# Modules already use ``logging.getLogger(__name__)``; this module is the single
# place that attaches handlers so those records actually reach a file (and,
# optionally, stderr in CLI/debug mode).  Log lines are redacted before they are
# written because request URLs can contain signed tokens.

from __future__ import annotations

import logging
import os
import re
import sys
import tempfile
from contextlib import suppress
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILENAME = "app.log"
LOG_DIR_ENV = "SC_LOG_DIR"
DEFAULT_LOG_SUBDIR = Path(".cache") / "logs"

_MAX_BYTES = 2 * 1024 * 1024
_BACKUP_COUNT = 3

_FILE_HANDLER_ATTR = "_oste_file_handler"
_STREAM_HANDLER_ATTR = "_oste_stream_handler"

# Network/HTTP libraries are extremely chatty at DEBUG. Keep their records out
# of the file unless the user explicitly asked for debug logging.
_NOISY_LOGGERS = (
    "httpcore",
    "httpcore2",
    "httpx",
    "httpx2",
    "urllib3",
    "urllib3.connectionpool",
    "curl_cffi",
)

# Do not log signed URLs, auth headers or bearer tokens verbatim.
_REDACT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"(?i)([?&](?:token|sig|signature|expires|exp|key|auth|password|"
            r"passwd|apikey|api_key|session)=)[^&\s]+"
        ),
        r"\1***",
    ),
    (
        re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]+"),
        r"\1***",
    ),
    (
        re.compile(
            r"(?i)\b(authorization|cookie|set-cookie)\s*[:=]\s*"
            r"(?:bearer\s+)?[^\s,;]+"
        ),
        r"\1: ***",
    ),
)


def redact(value: object) -> str:
    """Return ``value`` as text with credentials/signatures masked."""
    text = str(value)
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class RedactingFormatter(logging.Formatter):
    """Formatter that redacts the final message, including tracebacks."""

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def get_log_dir() -> Path:
    """Directory used for application logs (overridable with ``SC_LOG_DIR``)."""
    override = os.environ.get(LOG_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return _base_dir() / DEFAULT_LOG_SUBDIR


def get_log_path() -> Path:
    return get_log_dir() / LOG_FILENAME


def _remove_managed_handlers(root: logging.Logger) -> None:
    for handler in list(root.handlers):
        if getattr(handler, _FILE_HANDLER_ATTR, False) or getattr(
            handler, _STREAM_HANDLER_ATTR, False
        ):
            root.removeHandler(handler)
            with suppress(OSError):
                handler.close()


def _make_file_handler(log_dir: Path) -> logging.Handler:
    handler: logging.Handler
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_dir / LOG_FILENAME,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError:
        # A read-only working directory must not prevent the app from starting.
        fallback = Path(tempfile.gettempdir()) / "streamingcommunity-logs"
        fallback.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            fallback / LOG_FILENAME,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )

    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        RedactingFormatter(
            "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    setattr(handler, _FILE_HANDLER_ATTR, True)
    return handler


def setup_logging(
    *,
    debug: bool = False,
    stream: bool = False,
    log_dir: str | os.PathLike[str] | None = None,
) -> Path:
    """Configure the root logger and return the active log file path.

    * The rotating file handler always records at ``DEBUG``.
    * A stderr handler is only added when ``stream`` is true (CLI/debug mode),
      because writing to stderr while the Textual UI owns the terminal would
      corrupt the screen.
    * Calling this repeatedly replaces the handlers managed by this module
      instead of stacking duplicates.
    """
    root = logging.getLogger()
    _remove_managed_handlers(root)

    target_dir = Path(log_dir).expanduser() if log_dir is not None else get_log_dir()
    file_handler = _make_file_handler(target_dir)
    root.addHandler(file_handler)
    root.setLevel(logging.DEBUG)

    noisy_level = logging.DEBUG if debug else logging.WARNING
    for logger_name in _NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(noisy_level)

    if stream:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setLevel(logging.DEBUG if debug else logging.WARNING)
        stream_handler.setFormatter(RedactingFormatter("%(levelname)s: %(message)s"))
        setattr(stream_handler, _STREAM_HANDLER_ATTR, True)
        root.addHandler(stream_handler)

    return Path(file_handler.baseFilename)


def reset_logging() -> None:
    """Remove handlers installed by :func:`setup_logging` (used by tests)."""
    root = logging.getLogger()
    _remove_managed_handlers(root)
    root.setLevel(logging.WARNING)
    for logger_name in _NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.NOTSET)
