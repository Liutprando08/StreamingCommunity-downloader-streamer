# Tests for the cross-platform media-player detection and launch commands used
# by the streaming pipeline (macOS/Wayland previously failed with "no player
# found" because detection was PATH-only and mpv was forced to --vo=x11).

from __future__ import annotations

import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler
from unittest import mock

from StreamingCommunity.streaming import player as player_mod
from StreamingCommunity.streaming.session import is_direct_media_url
from StreamingCommunity.utils import domain_check


def _make_executable(directory: str, name: str) -> str:
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("#!/bin/sh\nexit 0\n")
    os.chmod(path, 0o755)
    return path


class TestResolveBinary(unittest.TestCase):
    def test_prefers_path_lookup(self):
        with mock.patch.object(player_mod.shutil, "which", return_value="/usr/bin/mpv"):
            self.assertEqual(player_mod._resolve_binary("mpv"), "/usr/bin/mpv")

    def test_finds_absolute_fallback_when_not_on_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = _make_executable(tmp, "mpv")
            with mock.patch.object(player_mod.shutil, "which", return_value=None):
                with mock.patch.object(
                    player_mod, "_app_binary_dir", return_value=None
                ):
                    with mock.patch.object(
                        player_mod, "_app_bundle_paths", return_value=[fake]
                    ):
                        self.assertEqual(player_mod._resolve_binary("mpv"), fake)

    def test_rejects_non_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mpv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("not exec")
            with mock.patch.object(player_mod.shutil, "which", return_value=None):
                with mock.patch.object(
                    player_mod, "_app_binary_dir", return_value=None
                ):
                    with mock.patch.object(
                        player_mod, "_app_bundle_paths", return_value=[path]
                    ):
                        self.assertIsNone(player_mod._resolve_binary("mpv"))

    def test_returns_none_when_missing(self):
        with mock.patch.object(player_mod.shutil, "which", return_value=None):
            with mock.patch.object(player_mod, "_app_binary_dir", return_value=None):
                with mock.patch.object(
                    player_mod, "_app_bundle_paths", return_value=[]
                ):
                    self.assertIsNone(player_mod._resolve_binary("mpv"))


class TestDetectPlayer(unittest.TestCase):
    def test_returns_resolved_path(self):
        with mock.patch.object(player_mod, "_resolve_binary", return_value="/opt/mpv"):
            detected = player_mod.detect_player()
        self.assertIsNotNone(detected)
        self.assertEqual(detected["name"], "mpv")
        self.assertEqual(detected["path"], "/opt/mpv")

    def test_preferred_player_wins(self):
        def fake_resolve(name):
            return f"/usr/bin/{name}"

        with mock.patch.object(player_mod, "_resolve_binary", side_effect=fake_resolve):
            detected = player_mod.detect_player("ffplay")
        self.assertEqual(detected["name"], "ffplay")

    def test_none_when_no_player(self):
        with mock.patch.object(player_mod, "_resolve_binary", return_value=None):
            self.assertIsNone(player_mod.detect_player())


class TestMpvCommand(unittest.TestCase):
    def _cmd(self):
        spec = next(p for p in player_mod.PLAYER_CANDIDATES if p["name"] == "mpv")
        return spec["build_cmd"]("/usr/local/bin/mpv", "http://x/y.m3u8", {"User-Agent": "UA"})

    def test_does_not_force_x11(self):
        self.assertNotIn("--vo=x11", self._cmd())

    def test_uses_portable_video_output(self):
        self.assertIn("--vo=gpu-next,gpu", self._cmd())

    def test_enables_hardware_decoding(self):
        self.assertIn("--hwdec=auto-safe", self._cmd())
        self.assertNotIn("--hwdec=no", self._cmd())

    def test_forwards_headers(self):
        self.assertIn("--http-header-fields=User-Agent: UA", self._cmd())


class TestVlcCommand(unittest.TestCase):
    def _cmd(self, headers):
        spec = next(p for p in player_mod.PLAYER_CANDIDATES if p["name"] == "vlc")
        return spec["build_cmd"]("/usr/bin/vlc", "http://x", headers)

    def test_forwards_user_agent_and_referer(self):
        cmd = self._cmd({"User-Agent": "UA", "Referer": "http://ref"})
        self.assertIn("--http-user-agent=UA", cmd)
        self.assertIn("--http-referrer=http://ref", cmd)

    def test_handles_missing_headers(self):
        cmd = self._cmd({})
        self.assertEqual(cmd[-1], "http://x")


class TestFfplayCommand(unittest.TestCase):
    def test_forwards_crlf_headers(self):
        spec = next(p for p in player_mod.PLAYER_CANDIDATES if p["name"] == "ffplay")
        cmd = spec["build_cmd"]("/usr/bin/ffplay", "http://x", {"User-Agent": "UA"})
        index = cmd.index("-headers")
        self.assertEqual(cmd[index + 1], "User-Agent: UA\r\n")


class _RangeHandler(BaseHTTPRequestHandler):
    data = b"0123456789abcdef" * 64

    def log_message(self, *args):
        pass

    def do_GET(self):
        range_header = self.headers.get("Range")
        if range_header:
            start_s, end_s = range_header.split("=", 1)[1].split("-", 1)
            start = int(start_s)
            end = int(end_s) if end_s else len(self.data) - 1
            body = self.data[start : end + 1]
            self.send_response(206)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(self.data)}")
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(self.data)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(self.data)


class TestDirectMedia(unittest.TestCase):
    def test_is_direct_media_url(self):
        self.assertTrue(is_direct_media_url("https://cdn.example.com/video.mp4"))
        self.assertTrue(is_direct_media_url("https://cdn.example.com/clip.MP4?token=abc"))
        self.assertTrue(is_direct_media_url("http://x/y/video.webm"))
        self.assertFalse(is_direct_media_url("https://x/master.m3u8"))
        self.assertFalse(is_direct_media_url("https://x/playlist.m3u8?key=1"))
        self.assertFalse(is_direct_media_url("not-a-url"))
        self.assertFalse(is_direct_media_url(""))

    def test_proxy_forwards_media_and_ranges(self):
        from http.server import ThreadingHTTPServer
        from types import SimpleNamespace
        from urllib.parse import quote
        from urllib.request import Request, urlopen

        from StreamingCommunity.streaming.server import ProxyServer

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), _RangeHandler)
        threading.Thread(target=upstream.serve_forever, daemon=True).start()
        session = SimpleNamespace(headers={"User-Agent": "test"}, proxy_port=0, cache=None)
        proxy = ProxyServer(session)
        port = proxy.start()
        try:
            upstream_url = f"http://127.0.0.1:{upstream.server_port}/video.mp4"
            media_url = f"http://127.0.0.1:{port}/media/{quote(upstream_url, safe=":/")}"

            with urlopen(Request(media_url, headers={"Range": "bytes=10-19"}), timeout=10) as response:
                self.assertEqual(response.status, 206)
                self.assertEqual(response.read(), b"abcdef0123")
                self.assertEqual(response.headers["Content-Range"], "bytes 10-19/1024")

            with urlopen(Request(media_url, method="HEAD"), timeout=10) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["Content-Length"], "1024")

            with urlopen(media_url, timeout=10) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(len(response.read()), 1024)
        finally:
            proxy.stop()
            upstream.shutdown()
            upstream.server_close()

    def test_domain_check_animeworld_pattern(self):
        html = '<html><body>Nuovo link <a href="https://www.animeworld.ac/">qui</a></body></html>'
        self.assertEqual(
            domain_check._extract_domain(html, domain_check.ANIMEWORLD_URL_PATTERN),
            "https://www.animeworld.ac",
        )
        html2 = "https://animeworld.to/"
        self.assertEqual(
            domain_check._extract_domain(html2, domain_check.ANIMEWORLD_URL_PATTERN),
            "https://animeworld.to",
        )


if __name__ == "__main__":
    unittest.main()
