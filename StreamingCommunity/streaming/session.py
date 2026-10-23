from __future__ import annotations

import logging
import signal
import threading
from urllib.parse import urlparse

from StreamingCommunity.utils.console.shared import console

logger = logging.getLogger(__name__)

DIRECT_MEDIA_SUFFIXES = (".mp4", ".m4v", ".webm", ".mkv")


def is_direct_media_url(url: str) -> bool:
    """True for a plain media file, which must not be parsed as HLS."""
    try:
        path = urlparse(str(url)).path.lower()
    except (TypeError, ValueError):
        return False
    return path.endswith(DIRECT_MEDIA_SUFFIXES)


class StreamSession:
    def __init__(
        self,
        playlist_url: str,
        headers: dict,
        output_dir: str | None = None,
        port: int = 0,
        preferred_player: str | None = None,
        direct_media: bool = False,
    ):
        self.playlist_url = playlist_url
        self.headers = headers or {}
        self.output_dir = output_dir
        self.preferred_player = preferred_player
        self.direct_media = bool(direct_media or is_direct_media_url(playlist_url))

        self.proxy_port = port
        self.cache = None
        self._server = None
        self._player = None
        self._original_sigint = None

    def start(self) -> bool:
        from .cache import SegmentCache

        self.cache = SegmentCache(max_size_mb=50)
        from .server import ProxyServer

        self._server = ProxyServer(self, port=self.proxy_port)
        self.proxy_port = self._server.start()
        from urllib.parse import quote

        encoded_url = quote(self.playlist_url, safe=":/")
        route = "media" if self.direct_media else "playlist"
        proxy_playlist_url = (
            f"http://127.0.0.1:{self.proxy_port}/{route}/{encoded_url}"
        )
        from .player import PlayerLauncher

        self._player = PlayerLauncher(self)
        if not self._player.launch(proxy_playlist_url, self.preferred_player):
            console.print("[red]Failed to launch media player")
            self.stop()
            return False

        player_name = (
            self._player._player["name"] if self._player._player else "unknown"
        )
        console.print(
            f"[green]Streaming via {player_name} on http://127.0.0.1:{self.proxy_port}"
        )
        self._install_signal_handlers()

        return True

    def wait(self):
        if self._player:
            exit_code = self._player.wait()
            console.print(f"[dim]Player exited with code {exit_code}")

    def stop(self):
        if self._original_sigint:
            signal.signal(signal.SIGINT, self._original_sigint)

        if self._player:
            self._player.stop()
        if self._server:
            self._server.stop()
        if self.cache:
            self.cache.clear()

        console.print("[dim]Streaming session ended")

    def _install_signal_handlers(self):
        # ``signal.signal`` only works on the main thread: the TUI runs the
        # stream in a worker thread, so skip installing the SIGINT handler there
        # instead of crashing with "signal only works in main thread".
        if threading.current_thread() is not threading.main_thread():
            logger.debug("Skipping SIGINT handler (not on main thread)")
            return

        self._original_sigint = signal.getsignal(signal.SIGINT)

        def handler(signum, frame):
            console.print("\n[yellow]Stopping stream...")
            self.stop()

        signal.signal(signal.SIGINT, handler)


def stream_content(
    playlist_url: str,
    headers: dict,
    output_dir: str | None = None,
    port: int = 0,
    preferred_player: str | None = None,
    direct_media: bool = False,
):
    session = StreamSession(
        playlist_url=playlist_url,
        headers=headers,
        output_dir=output_dir,
        port=port,
        preferred_player=preferred_player,
        direct_media=direct_media,
    )

    if not session.start():
        return

    try:
        session.wait()
    finally:
        session.stop()
