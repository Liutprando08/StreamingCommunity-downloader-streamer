"""Configuration, session and credential storage.

Mirrors ``internal/config``: JSON files under ``~/.config/zlib``, mode 0600,
with directory creation at 0700. ``ZLIB_CONFIG_DIR`` overrides the directory
for tests and sandboxes.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..kindle import KindleConfig
from ..weread.errors import NotLoggedIn
from ..weread.client import Credentials

__all__ = [
    "CONFIG_DIR_ENV",
    "config_dir",
    "Config",
    "Session",
    "KindleConfig",
    "config_path",
    "session_path",
    "kindle_path",
    "weread_path",
    "load_config",
    "save_config",
    "load_session",
    "save_session",
    "load_kindle",
    "save_kindle",
    "load_weread",
    "save_weread",
    "weread_saver",
    "remove_weread",
]

CONFIG_DIR_ENV = "ZLIB_CONFIG_DIR"
_weread_lock = threading.RLock()


def config_dir() -> Path:
    override = os.environ.get(CONFIG_DIR_ENV, "").strip()
    if override:
        return Path(override)
    return Path.home() / ".config" / "zlib"


def config_path() -> Path:
    return config_dir() / "config.json"


def session_path() -> Path:
    return config_dir() / "session.json"


def kindle_path() -> Path:
    return config_dir() / "kindle.json"


def weread_path() -> Path:
    return config_dir() / "weread.json"


@dataclass
class Config:
    theme: str = ""
    last_login_email: str = ""
    user_mirrors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.theme:
            data["theme"] = self.theme
        if self.last_login_email:
            data["last_login_email"] = self.last_login_email
        if self.user_mirrors:
            data["user_mirrors"] = list(self.user_mirrors)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        mirrors = data.get("user_mirrors")
        return cls(
            theme=data.get("theme") if isinstance(data.get("theme"), str) else "",
            last_login_email=(
                data.get("last_login_email")
                if isinstance(data.get("last_login_email"), str)
                else ""
            ),
            user_mirrors=[item for item in mirrors if isinstance(item, str)]
            if isinstance(mirrors, list)
            else [],
        )


@dataclass
class Session:
    cookies: dict[str, str] = field(default_factory=dict)
    domain: str = ""
    mode: str = ""

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"cookies": dict(self.cookies), "domain": self.domain}
        if self.mode:
            data["mode"] = self.mode
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        cookies = data.get("cookies")
        return cls(
            cookies={str(k): str(v) for k, v in cookies.items()} if isinstance(cookies, dict) else {},
            domain=data.get("domain") if isinstance(data.get("domain"), str) else "",
            mode=data.get("mode") if isinstance(data.get("mode"), str) else "",
        )


def _read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_path, path)
        os.chmod(path, 0o600)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_config(path: Path | None = None) -> Config:
    return Config.from_dict(_read_json(Path(path) if path else config_path()))


def save_config(config: Config, path: Path | None = None) -> None:
    _write_json(Path(path) if path else config_path(), config.to_dict())


def load_session(path: Path | None = None) -> Session:
    return Session.from_dict(_read_json(Path(path) if path else session_path()))


def save_session(session: Session, path: Path | None = None) -> None:
    _write_json(Path(path) if path else session_path(), session.to_dict())


def load_kindle(path: Path | None = None) -> KindleConfig:
    data = _read_json(Path(path) if path else kindle_path())
    if not isinstance(data, dict):
        raise ValueError("kindle config must be an object")
    return KindleConfig.from_dict(data)


def save_kindle(config: KindleConfig, path: Path | None = None) -> None:
    _write_json(Path(path) if path else kindle_path(), config.to_dict())


def load_weread(path: Path | None = None) -> Credentials:
    target = Path(path) if path else weread_path()
    try:
        data = _read_json(target)
    except FileNotFoundError as exc:
        raise NotLoggedIn("not logged in to WeRead") from exc
    if not isinstance(data, dict):
        raise NotLoggedIn("not logged in to WeRead")
    creds = Credentials.from_dict(data)
    if not creds.valid():
        raise NotLoggedIn("not logged in to WeRead")
    return creds


def save_weread(creds: Credentials, path: Path | None = None) -> None:
    with _weread_lock:
        _write_json(Path(path) if path else weread_path(), creds.to_dict())


def weread_saver(expected: Credentials, path: Path | None = None):
    """Build a saver that only updates the login it loaded."""
    target = Path(path) if path else weread_path()

    def save(next_creds: Credentials) -> None:
        nonlocal expected
        with _weread_lock:
            current = load_weread(target)
            if current != expected:
                raise RuntimeError("WeRead login changed; retry with the current account")
            save_weread(next_creds, target)
            expected = next_creds

    return save


def remove_weread(path: Path | None = None) -> bool:
    with _weread_lock:
        try:
            os.unlink(Path(path) if path else weread_path())
        except FileNotFoundError:
            return False
        return True
