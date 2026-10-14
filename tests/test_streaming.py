# Tests for the cross-platform media-player detection and launch commands used
# by the streaming pipeline (macOS/Wayland previously failed with "no player
# found" because detection was PATH-only and mpv was forced to --vo=x11).

from __future__ import annotations

import os
import tempfile
import threading
import unittest
from unittest import mock

from StreamingCommunity.streaming import player as player_mod


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


class TestSignalHandlers(unittest.TestCase):
    def test_noop_off_main_thread(self):
        from StreamingCommunity.streaming.session import StreamSession

        session = StreamSession("http://example/master.m3u8", {"User-Agent": "UA"})
        session._original_sigint = "sentinel"
        errors: list[BaseException] = []

        def run():
            try:
                session._install_signal_handlers()
            except BaseException as exc:  # noqa: BLE001 - report back to main thread
                errors.append(exc)

        worker = threading.Thread(target=run)
        worker.start()
        worker.join()

        self.assertEqual(errors, [])
        # Off the main thread the handler must not be (and cannot be) replaced.
        self.assertEqual(session._original_sigint, "sentinel")


if __name__ == "__main__":
    unittest.main()
