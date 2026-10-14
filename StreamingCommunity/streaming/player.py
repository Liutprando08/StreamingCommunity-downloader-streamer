import os
import platform
import shutil
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


def _format_headers(headers: dict) -> str:
    return ",".join(f"{k}: {v}" for k, v in headers.items())


def _ffplay_headers(headers: dict) -> str:
    # ffplay expects CRLF-terminated header lines.
    return "".join(f"{k}: {v}\r\n" for k, v in headers.items())


def _system() -> str:
    return platform.system().lower()


def _app_binary_dir() -> Optional[str]:
    """Directory where the app keeps its own downloaded binaries.

    Mirrors ``setup.binary_paths.BinaryPaths.get_binary_directory`` without
    importing the setup package (which runs the binary checks on import).
    """
    home = os.path.expanduser("~")
    system = _system()
    if system == "darwin":
        return os.path.join(home, "Applications", "binary", "/opt/homebrew/bin/")
    if system == "linux":
        return os.path.join(home, ".local", "bin", "binary")
    if system == "windows":
        drive = os.path.splitdrive(home)[0] or os.environ.get("SystemDrive", "C:")
        return os.path.join(drive + os.sep, "binary")
    return None


def _app_bundle_paths(name: str) -> list:
    """Absolute paths for players that are not always on ``PATH``.

    macOS keeps Homebrew tools outside the default ``PATH`` seen by
    GUI-launched apps and ships VLC/mpv inside ``.app`` bundles; Windows
    installers place the binaries under Program Files / scoop / chocolatey.
    """
    home = os.path.expanduser("~")
    system = _system()

    if system == "darwin":
        base = [
            f"/opt/homebrew/bin/{name}",
            f"/usr/local/bin/{name}",
            f"/opt/local/bin/{name}",
        ]
        if name == "mpv":
            return [
                "/Applications/mpv.app/Contents/MacOS/mpv",
                os.path.join(home, "Applications/mpv.app/Contents/MacOS/mpv"),
                *base,
            ]
        if name == "vlc":
            return [
                "/Applications/VLC.app/Contents/MacOS/vlc",
                os.path.join(home, "Applications/VLC.app/Contents/MacOS/vlc"),
                *base,
            ]
        return base

    if system == "windows":
        exe = f"{name}.exe"
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get(
            "ProgramFiles(x86)", r"C:\Program Files (x86)"
        )
        local_appdata = os.environ.get(
            "LOCALAPPDATA", os.path.join(home, "AppData", "Local")
        )
        candidates = [
            os.path.join(program_files, name, exe),
            os.path.join(program_files_x86, name, exe),
            os.path.join(local_appdata, "Programs", name, exe),
            os.path.join(home, "scoop", "shims", exe),
            os.path.join(r"C:\ProgramData", "chocolatey", "bin", exe),
        ]
        if name == "vlc":
            candidates.append(os.path.join(program_files, "VideoLAN", "VLC", "vlc.exe"))
            candidates.append(
                os.path.join(program_files_x86, "VideoLAN", "VLC", "vlc.exe")
            )
        return candidates

    return [
        f"/usr/bin/{name}",
        f"/usr/local/bin/{name}",
        f"/snap/bin/{name}",
        f"/var/lib/flatpak/exports/bin/{name}",
        os.path.join(home, ".local", "bin", name),
    ]


def _is_executable(path: str) -> bool:
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def _resolve_binary(name: str) -> Optional[str]:
    """Locate ``name`` on ``PATH`` or in well-known per-OS install locations."""
    found = shutil.which(name)
    if found:
        return found

    candidates = []
    binary_dir = _app_binary_dir()
    if binary_dir:
        candidates.append(os.path.join(binary_dir, name))
        candidates.append(os.path.join(binary_dir, f"{name}.exe"))
    candidates.extend(_app_bundle_paths(name))

    for candidate in candidates:
        if _is_executable(candidate):
            return candidate

    return None


def _vlc_cmd(path: str, url: str, headers: dict) -> list:
    cmd = [path, "--network-caching=3000"]
    for key, value in headers.items():
        low = key.lower()
        if low == "user-agent":
            cmd.append(f"--http-user-agent={value}")
        elif low == "referer":
            cmd.append(f"--http-referrer={value}")
    cmd.append(url)
    return cmd


PLAYER_CANDIDATES = [
    {
        "name": "mpv",
        "detect": ["mpv", "--version"],
        "build_cmd": lambda path, url, headers: [
            path,
            "--profile=high-quality",
            "--hwdec=auto-safe",
            # ``--vo=x11`` is X11-only and breaks macOS/Wayland; ``gpu-next``
            # with a ``gpu`` fallback works on every desktop platform.
            "--vo=gpu-next,gpu",
            f"--http-header-fields={_format_headers(headers)}",
            url,
        ],
    },
    {
        "name": "vlc",
        "detect": ["vlc", "--version"],
        "build_cmd": lambda path, url, headers: _vlc_cmd(path, url, headers),
    },
    {
        "name": "ffplay",
        "detect": ["ffplay", "-version"],
        "build_cmd": lambda path, url, headers: [
            path,
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-headers",
            _ffplay_headers(headers),
            url,
        ],
    },
]


def detect_player(preferred: Optional[str] = None) -> Optional[dict]:
    candidates = PLAYER_CANDIDATES

    if preferred:
        candidates = [p for p in PLAYER_CANDIDATES if p["name"] == preferred] + [
            p for p in PLAYER_CANDIDATES if p["name"] != preferred
        ]

    for player in candidates:
        path = _resolve_binary(player["detect"][0])
        if path:
            logger.info(f"Found player: {player['name']} at {path}")
            resolved = dict(player)
            resolved["path"] = path
            return resolved

    return None


class PlayerLauncher:
    def __init__(self, session):
        self.session = session
        self._process: Optional[subprocess.Popen] = None
        self._player = None

    def launch(self, url: str, preferred_player: Optional[str] = None) -> bool:
        """Launch the player with the given URL. Returns True on success."""
        if not url.startswith(("http://", "https://")):
            logger.error("Invalid URL scheme for player: %s", url[:40])
            return False

        self._player = detect_player(preferred_player)
        if not self._player:
            logger.error(
                "No media player found. Install one of: mpv (recommended), vlc "
                "or ffplay (ffmpeg). macOS: 'brew install mpv' or install VLC.app; "
                "Windows: scoop/choco or the official installers; Linux: your "
                "package manager."
            )
            return False

        binary = self._player.get("path") or self._player["detect"][0]
        cmd = self._player["build_cmd"](binary, url, self.session.headers)
        logger.info(f"Launching: {' '.join(cmd)}")

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info(f"Player launched (PID: {self._process.pid})")
            return True
        except FileNotFoundError:
            logger.error(f"Player binary not found: {self._player['detect'][0]}")
            return False
        except Exception as e:
            logger.error(f"Failed to launch player: {e}")
            return False

    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None

    def wait(self) -> int:

        if self._process is None:
            return -1
        return self._process.wait()

    def stop(self):

        if self._process and self.is_running():
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            except Exception:
                pass
