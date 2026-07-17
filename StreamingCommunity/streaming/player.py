import shutil
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

PLAYER_CANDIDATES = [
    {
        "name": "mpv",
        "detect": ["mpv", "--version"],
        "build_cmd": lambda url, headers: [
            "mpv",
            "--profile=high-quality",
            "--hwdec=no",
            "--vo=x11",
            f"--http-header-fields={_format_headers(headers)}",
            url,
        ],
    },
    {
        "name": "vlc",
        "detect": ["vlc", "--version"],
        "build_cmd": lambda url, headers: [
            "vlc",
            "--network-caching=3000",
            *(
                ["--http-referrer", headers["referer"]]
                if headers.get("referer")
                else []
            ),
            url,
        ],
    },
    {
        "name": "ffplay",
        "detect": ["ffplay", "-version"],
        "build_cmd": lambda url, headers: [
            "ffplay",
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            url,
        ],
    },
]


def _format_headers(headers: dict) -> str:
    return ",".join(f"{k}: {v}" for k, v in headers.items())


def detect_player(preferred: Optional[str] = None) -> Optional[dict]:
    candidates = PLAYER_CANDIDATES

    if preferred:
        candidates = [p for p in PLAYER_CANDIDATES if p["name"] == preferred] + [
            p for p in PLAYER_CANDIDATES if p["name"] != preferred
        ]

    for player in candidates:
        if shutil.which(player["detect"][0]):
            logger.info(f"Found player: {player['name']}")
            return player

    return None


class PlayerLauncher:
    def __init__(self, session):
        self.session = session
        self._process: Optional[subprocess.Popen] = None
        self._player = None

    def launch(self, url: str, preferred_player: Optional[str] = None) -> bool:
        """Launch the player with the given URL. Returns True on success."""
        self._player = detect_player(preferred_player)
        if not self._player:
            logger.error("No media player found (install mpv, vlc, or ffplay)")
            return False

        cmd = self._player["build_cmd"](url, self.session.headers)
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
