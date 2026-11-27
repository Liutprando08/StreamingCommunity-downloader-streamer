"""Headless entry points for the Android (Kivy) shell.

Only the services that already download through the ``yt-dlp`` engine are
exposed here (``streamingcommunity`` and ``altadefinizione``).  Keeping this
module free of ``StreamingCommunity`` imports is important: ``prepare()`` must
run *before* :class:`~StreamingCommunity.utils.config.ConfigManager` is
instantiated, because that is when the configuration directory is resolved.
"""

from __future__ import annotations

import os
import sys

APP_NAME = "StreamingCommunity"
HOME_ENV = "STREAMINGCOMMUNITY_HOME"
OUTPUT_ENV = "STREAMINGCOMMUNITY_OUTPUT"


def is_android() -> bool:
    """Return True when running inside a python-for-android bootstrap."""
    if os.environ.get("ANDROID_ARGUMENT") or os.environ.get("ANDROID_PRIVATE"):
        return True
    return "android" in sys.platform.lower()


def _android_private_dir() -> str | None:
    for key in ("ANDROID_PRIVATE", "ANDROID_APP_PATH"):
        value = os.environ.get(key)
        if value:
            return value

    try:
        from jnius import autoclass  # type: ignore[import-not-found]

        context = autoclass("org.kivy.android.PythonActivity").mActivity
        return str(context.getFilesDir().getAbsolutePath())
    except Exception:
        return None


def default_home() -> str:
    """Return the writable directory used for config, output and history."""
    configured = os.environ.get(HOME_ENV)
    if configured:
        return os.path.abspath(os.path.expanduser(configured))

    if is_android():
        private = _android_private_dir()
        if private:
            return os.path.abspath(private)

    # Desktop fallback: the repository root (parent of the package).
    return os.path.abspath(
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    )


def prepare(home: str | None = None, output_root: str | None = None) -> dict[str, str]:
    """Configure environment variables and directories for the engine.

    Returns a small dict describing the resolved paths so the UI can display
    them.  Call this exactly once, before importing any other
    ``StreamingCommunity`` module.
    """
    resolved_home = os.path.abspath(os.path.expanduser(home)) if home else default_home()
    os.makedirs(resolved_home, exist_ok=True)

    resolved_output = (
        os.path.abspath(os.path.expanduser(output_root))
        if output_root
        else os.path.join(resolved_home, "Video")
    )
    os.makedirs(resolved_output, exist_ok=True)

    os.environ[HOME_ENV] = resolved_home
    os.environ[OUTPUT_ENV] = resolved_output

    conf_dir = os.path.join(resolved_home, "Conf")
    os.makedirs(conf_dir, exist_ok=True)

    # Relative output folders ("Video", "Serie", ...) resolve against CWD.
    # Android's default CWD is "/" and is not writable.
    try:
        os.chdir(resolved_home)
    except OSError:
        pass

    return {
        "home": resolved_home,
        "output": resolved_output,
        "conf": conf_dir,
    }
