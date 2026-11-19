"""The signed-in WeRead account's profile (mirrors ``internal/weread/user.go``)."""

from __future__ import annotations

from dataclasses import dataclass, field

from .client import Client, clean_text
from .errors import NotLoggedIn

NAME_FIELDS = ("name", "nickName", "nick", "user.name")


@dataclass
class UserInfo:
    name: str = ""
    keys: list[str] = field(default_factory=list)


def flatten_fields(raw: dict) -> dict:
    """Map top-level fields, and one level of nesting as ``parent.child``."""
    out: dict = {}
    for name, value in raw.items():
        cleaned_name = clean_text(str(name))
        out[cleaned_name] = value
        if isinstance(value, dict):
            for child, child_value in value.items():
                out[cleaned_name + "." + clean_text(str(child))] = child_value
    return out


def user_info(client: Client) -> UserInfo:
    vid = client.credentials().vid
    if not vid:
        raise NotLoggedIn("not logged in to WeRead")
    raw = client._call("GET", "/user", {"userVid": vid})
    if not isinstance(raw, dict):
        raw = {}
    fields = flatten_fields(raw)
    info = UserInfo(keys=sorted(fields))
    for name in NAME_FIELDS:
        value = fields.get(name)
        if isinstance(value, str):
            cleaned = clean_text(value.replace("\n", " "))
            if cleaned:
                info.name = cleaned
                break
    return info


def update_name(client: Client) -> str:
    info = user_info(client)
    if not info.name:
        return client.credentials().name
    with client._lock:
        if client._creds.name == info.name:
            return info.name
        client._creds.name = info.name
        if client._save is not None:
            try:
                client._save(client.credentials())
            except Exception as exc:  # noqa: BLE001 - surfaced to the caller
                from .errors import WeReadError

                raise WeReadError(f"save WeRead credentials: {exc}") from exc
        return info.name


__all__ = ["UserInfo", "flatten_fields", "user_info", "update_name"]
