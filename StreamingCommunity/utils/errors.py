# User-facing error translation.
#
# The application talks to many sites, external binaries and local files; raw
# exception strings are rarely actionable.  ``friendly_error`` maps the most
# common failures to a short message plus a suggested next step, and
# ``report_fatal_error`` is the single top-level reporter used by the CLI.

from __future__ import annotations

import errno
import json
import logging
import subprocess
from dataclasses import dataclass

from rich.markup import escape

from StreamingCommunity.utils.console.shared import console

logger = logging.getLogger(__name__)

_TIMEOUT_NAMES = {
    "timeouterror",
    "timeoutexception",
    "readtimeout",
    "connecttimeout",
    "pooltimeout",
    "writetimeout",
    "timeout",
}
_CONNECTION_NAMES = {
    "connecterror",
    "connectionerror",
    "connectionreseterror",
    "connectionrefusederror",
    "connectionabortederror",
    "networkerror",
    "proxyerror",
    "sslerror",
    "socketerror",
    "gaierror",
}
_MISSING_TOOL_HINTS = {
    "aria2c": "Install aria2c, or let the app download its bundled copy.",
    "ffmpeg": "Install ffmpeg and make sure it is available on PATH.",
    "ffprobe": "Install ffprobe (usually shipped with ffmpeg) and make sure it is on PATH.",
    "mp4decrypt": "Install Bento4 (mp4decrypt) or let the app download it.",
    "mpv": "Install mpv, or choose another player with --player vlc/ffplay.",
    "shaka-packager": "Install shaka-packager or let the app download it.",
    "vlc": "Install VLC, or choose another player with --player mpv/ffplay.",
    "ffplay": "Install ffplay (usually shipped with ffmpeg), or choose another player.",
}


@dataclass(frozen=True)
class ErrorInfo:
    """A short user-facing message and an optional suggested fix."""

    message: str
    hint: str = ""


def _status_code(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    candidates = [
        getattr(response, "status_code", None) if response is not None else None,
        getattr(exc, "status_code", None),
        getattr(exc, "code", None),
    ]
    for value in candidates:
        try:
            code = int(value)
        except (TypeError, ValueError):
            continue
        if 100 <= code <= 599:
            return code
    return None


def _type_names(exc: BaseException) -> set[str]:
    return {cls.__name__.lower().lstrip("_") for cls in type(exc).__mro__}


def _missing_tool(exc: BaseException) -> str | None:
    text = f"{exc} {getattr(exc, 'filename', '')}".lower()
    for tool, hint in _MISSING_TOOL_HINTS.items():
        if tool in text:
            return hint
    return None


def friendly_error(exc: BaseException) -> ErrorInfo:
    """Translate an exception into a concise message and a suggested fix."""
    if isinstance(exc, KeyboardInterrupt):
        return ErrorInfo("Interrupted by user.")

    status = _status_code(exc)
    if status is not None:
        if status in (401, 403):
            return ErrorInfo(
                f"Access denied (HTTP {status}).",
                "The site may require a login, a subscription, or a different "
                "region/VPN.",
            )
        if status == 404:
            return ErrorInfo(
                "The requested resource was not found (HTTP 404).",
                "The site may have changed its domain or the title may no longer "
                "be available.",
            )
        if status == 429:
            return ErrorInfo(
                "Too many requests (HTTP 429).",
                "Wait a few minutes, or reduce concurrent searches/downloads.",
            )
        if status == 451:
            return ErrorInfo(
                "Content is unavailable in this region (HTTP 451).",
                "A VPN may be required for this source.",
            )
        if 500 <= status <= 599:
            return ErrorInfo(
                f"The remote server failed (HTTP {status}).",
                "Try again later, or switch to another domain/mirror.",
            )

    names = _type_names(exc)
    if names & _TIMEOUT_NAMES:
        return ErrorInfo(
            "The request timed out.",
            "Check your connection, raise REQUESTS.timeout in Conf/config.json, "
            "or try again.",
        )
    if names & _CONNECTION_NAMES or isinstance(exc, ConnectionError):
        return ErrorInfo(
            "Could not connect to the remote server.",
            "Check your internet connection, proxy/VPN settings, and the site "
            "domain in Conf/domains.json.",
        )

    if isinstance(exc, (FileNotFoundError, PermissionError)):
        hint = _missing_tool(exc)
        if hint:
            return ErrorInfo("A required external tool is missing.", hint)

    if isinstance(exc, PermissionError):
        return ErrorInfo(
            "Permission denied while accessing a file or folder.",
            "Check file permissions and choose a writable output path.",
        )

    if isinstance(exc, FileNotFoundError):
        name = getattr(exc, "filename", None) or str(exc)
        return ErrorInfo(
            f"File not found: {name}",
            "Check the path in Conf/config.json and that the drive/location is "
            "available.",
        )

    if isinstance(exc, ModuleNotFoundError):
        module = getattr(exc, "name", None) or str(exc)
        return ErrorInfo(
            f"Missing Python dependency: {module}",
            "Run `pip install -e .` or `uv sync` to install the project dependencies.",
        )

    if isinstance(exc, subprocess.CalledProcessError):
        return ErrorInfo(
            f"An external command failed (exit code {exc.returncode}).",
            "Check the command output above and that the tool is installed correctly.",
        )

    if isinstance(exc, json.JSONDecodeError):
        return ErrorInfo(
            "A configuration file is not valid JSON.",
            f"{exc.msg} at line {exc.lineno}, column {exc.colno}. Fix the file, or "
            "delete it so it can be downloaded again.",
        )

    if isinstance(exc, OSError):
        if exc.errno == errno.ENOSPC:
            return ErrorInfo(
                "There is no space left on the destination device.",
                "Free some disk space or choose another output path.",
            )
        if exc.errno in (errno.EACCES, errno.EPERM):
            return ErrorInfo(
                "Permission denied by the operating system.",
                "Run the app as a user that can write to the output folder.",
            )
        if exc.errno == errno.ENOENT:
            return ErrorInfo(
                "A file or folder does not exist.",
                "Check the configured paths in Conf/config.json.",
            )

    message = str(exc).strip() or type(exc).__name__
    return ErrorInfo(message)


def report_fatal_error(exc: BaseException, *, debug: bool = False) -> None:
    """Print a friendly fatal error and, in debug mode, the full traceback."""
    info = friendly_error(exc)
    logger.error("Fatal error: %s", exc, exc_info=debug)

    console.print(f"\n[red]✖ {escape(info.message)}[/]")
    if info.hint:
        console.print(f"[yellow]→ {escape(info.hint)}[/]")

    if debug:
        console.print_exception(show_locals=False)
    else:
        console.print("[dim]Run with --debug for the full traceback.[/]")
