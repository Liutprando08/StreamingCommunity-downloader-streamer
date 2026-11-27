# 18.07.25 - 27.11.26: lazy tool resolution (no network / no downloads at import)

from __future__ import annotations

import os
import shutil
import sys
from functools import lru_cache
from typing import Optional, Tuple

# Logic
from .checker import (
    check_aria2c,
    check_bento4,
    check_ffmpeg,
    check_megatools,
    check_mp4dump,
    check_n_m3u8dl_re,
    check_shaka_packager,
)
from .device_install import check_device_prd_path, check_device_wvd_path

# Variable
is_binary_installation = getattr(sys, "frozen", False)

#: Android detection works even when ``platform.system()`` reports ``Linux``.
IS_ANDROID = bool(
    os.environ.get("ANDROID_ARGUMENT")
    or os.environ.get("ANDROID_PRIVATE")
    or os.environ.get("ANDROID_APP_PATH")
    or "android" in sys.platform.lower()
)

#: Names used for the bundled executables. Android requires ``lib*.so`` names
#: to be placed in the native library directory and executed from there.
_FFMPEG_NAMES = ("ffmpeg", "libffmpeg.so")
_FFPROBE_NAMES = ("ffprobe", "libffprobe.so")


def _android_native_lib_dir() -> str | None:
    """Return the APK native library directory (where ``lib*.so`` live)."""
    try:
        from jnius import autoclass  # type: ignore[import-not-found]

        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        return activity.getApplicationInfo().nativeLibraryDir
    except Exception:
        return None


def _android_private_dir() -> str | None:
    for key in ("ANDROID_PRIVATE", "ANDROID_APP_PATH"):
        value = os.environ.get(key)
        if value:
            return value
    return None


def _search_dirs() -> list[str]:
    """Directories that may contain bundled tools, in priority order."""
    dirs: list[str] = []

    explicit = os.environ.get("STREAMINGCOMMUNITY_BIN_DIR")
    if explicit:
        dirs.append(explicit)

    if IS_ANDROID:
        native = _android_native_lib_dir()
        if native:
            dirs.append(native)
        private = _android_private_dir()
        if private:
            dirs.extend((private, os.path.join(private, "bin")))
    else:
        home = os.environ.get("STREAMINGCOMMUNITY_HOME")
        if home:
            dirs.extend((home, os.path.join(home, "bin")))

    return [item for item in dirs if item and os.path.isdir(item)]


def _find_bundled(names: tuple[str, ...], env_var: str | None = None) -> str | None:
    """Find an executable by name in the configured/bundled locations."""
    if env_var:
        override = os.environ.get(env_var)
        if override and os.path.isfile(override):
            return override

    for directory in _search_dirs():
        for name in names:
            candidate = os.path.join(directory, name)
            if os.path.isfile(candidate):
                return candidate

    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


@lru_cache(maxsize=1)
def get_ffmpeg_path() -> str | None:
    """Resolve ffmpeg lazily.

    On Android only bundled/PATH tools are used: the desktop fallback would
    try to download an x86_64 build from GitHub.
    """
    if IS_ANDROID:
        return _find_bundled(_FFMPEG_NAMES, "STREAMINGCOMMUNITY_FFMPEG")

    found = _find_bundled(_FFMPEG_NAMES, "STREAMINGCOMMUNITY_FFMPEG")
    if found:
        return found

    path, _ = check_ffmpeg()
    return path


@lru_cache(maxsize=1)
def get_ffprobe_path() -> str | None:
    if IS_ANDROID:
        return _find_bundled(_FFPROBE_NAMES, "STREAMINGCOMMUNITY_FFPROBE")

    found = _find_bundled(_FFPROBE_NAMES, "STREAMINGCOMMUNITY_FFPROBE")
    if found:
        return found

    _, path = check_ffmpeg()
    return path


@lru_cache(maxsize=1)
def get_bento4_decrypt_path() -> str | None:
    if IS_ANDROID:
        return _find_bundled(("mp4decrypt", "libmp4decrypt.so"))
    return check_bento4()


@lru_cache(maxsize=1)
def get_mp4dump_path() -> str | None:
    if IS_ANDROID:
        return _find_bundled(("mp4dump", "libmp4dump.so"))
    return check_mp4dump()


@lru_cache(maxsize=1)
def get_megatools_path() -> str | None:
    if IS_ANDROID:
        # Desktop-only tool: never attempt a download on Android.
        return _find_bundled(("megatools",))
    return check_megatools()


@lru_cache(maxsize=1)
def get_n_m3u8dl_re_path() -> str | None:
    if IS_ANDROID:
        return _find_bundled(("N_m3u8DL-RE", "libN_m3u8DL-RE.so"))
    return check_n_m3u8dl_re()


@lru_cache(maxsize=1)
def get_shaka_packager_path() -> tuple[str | None, str | None] | str | None:
    if IS_ANDROID:
        return _find_bundled(("packager", "libpackager.so", "packager-linux-arm64"))
    return check_shaka_packager()


@lru_cache(maxsize=1)
def get_aria2c_path() -> str | None:
    if IS_ANDROID:
        return _find_bundled(("aria2c",))
    return check_aria2c()


@lru_cache(maxsize=1)
def get_wvd_path() -> str | None:
    """Locate the user supplied Widevine device file (``.wvd``)."""
    override = os.environ.get("STREAMINGCOMMUNITY_WVD")
    if override and os.path.isfile(override):
        return override

    if IS_ANDROID:
        home = os.environ.get("STREAMINGCOMMUNITY_HOME")
        if home:
            for directory in (home, os.path.join(home, "cdm")):
                found = _first_with_suffix(directory, ".wvd")
                if found:
                    return found
        return None

    return check_device_wvd_path()


@lru_cache(maxsize=1)
def get_prd_path() -> str | None:
    """Locate the user supplied PlayReady device file (``.prd``)."""
    override = os.environ.get("STREAMINGCOMMUNITY_PRD")
    if override and os.path.isfile(override):
        return override

    if IS_ANDROID:
        home = os.environ.get("STREAMINGCOMMUNITY_HOME")
        if home:
            for directory in (home, os.path.join(home, "cdm")):
                found = _first_with_suffix(directory, ".prd")
                if found:
                    return found
        return None

    return check_device_prd_path()


def _first_with_suffix(directory: str, suffix: str) -> str | None:
    try:
        for name in sorted(os.listdir(directory)):
            if name.lower().endswith(suffix):
                path = os.path.join(directory, name)
                if os.path.isfile(path):
                    return path
    except OSError:
        return None
    return None


def get_is_binary_installation() -> bool:
    return is_binary_installation


def reset_tool_cache() -> None:
    """Clear cached tool paths (used after the user imports a CDM file)."""
    for func in (
        get_ffmpeg_path,
        get_ffprobe_path,
        get_bento4_decrypt_path,
        get_mp4dump_path,
        get_megatools_path,
        get_n_m3u8dl_re_path,
        get_shaka_packager_path,
        get_aria2c_path,
        get_wvd_path,
        get_prd_path,
    ):
        func.cache_clear()


def get_info_wvd(cdm_device_path):
    if cdm_device_path is not None:
        from pywidevine.device import Device

        device = Device.load(cdm_device_path)

        # Extract client info
        info = {ci.name: ci.value for ci in device.client_id.client_info}
        model = info.get("model_name", "N/A")

        device_name = info.get("device_name", "").lower()
        build_info = info.get("build_info", "").lower()

        # Extract device type
        is_emulator = (
            any(x in device_name for x in ["generic", "sdk", "emulator", "x86"])
            or "test-keys" in build_info
            or "userdebug" in build_info
        )

        if "tv" in model.lower():
            dev_type = "Android TV"
        elif is_emulator:
            dev_type = "Android Emulator"
        else:
            dev_type = "Android Phone"

        return (
            f"[cyan]Load WVD: "
            f"[red]L{device.security_level} [cyan]| [red]{dev_type} [cyan]| "
            f"[cyan]SysID: [red]{device.system_id}"
        )


def get_info_prd(cdm_device_path):
    if cdm_device_path is not None:
        from pyplayready.device import Device

        device = Device.load(cdm_device_path)
        cert_chain = device.group_certificate
        leaf_cert = cert_chain.get(0)

        return (
            f"[cyan]Load PRD: "
            f"[red]SL{device.security_level} [cyan]| "
            f"[yellow]{leaf_cert.get_name()} "
        )
