from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from StreamingCommunity.zlib_engine.config import (
    Config,
    Session,
    config_path,
    load_config,
    load_kindle,
    load_session,
    load_weread,
    remove_weread,
    save_config,
    save_kindle,
    save_session,
    save_weread,
    weread_saver,
)
from StreamingCommunity.zlib_engine.kindle import KindleConfig
from StreamingCommunity.zlib_engine.weread import Credentials, NotLoggedIn
from StreamingCommunity.zlib_engine.config import CONFIG_DIR_ENV


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._old = os.environ.get(CONFIG_DIR_ENV)
        os.environ[CONFIG_DIR_ENV] = self._tmp.name
        self.addCleanup(self._restore_env)

    def _restore_env(self) -> None:
        if self._old is None:
            os.environ.pop(CONFIG_DIR_ENV, None)
        else:
            os.environ[CONFIG_DIR_ENV] = self._old

    def test_config_round_trip_without_null_fields(self) -> None:
        save_config(Config(theme="dark", last_login_email="reader@example.com"))
        loaded = load_config()
        self.assertEqual(loaded.theme, "dark")
        self.assertEqual(loaded.last_login_email, "reader@example.com")
        self.assertEqual(loaded.user_mirrors, [])
        raw = Path(config_path()).read_text(encoding="utf-8")
        self.assertNotIn("null", raw)
        self.assertEqual(stat.S_IMODE(Path(config_path()).stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(Path(self._tmp.name).stat().st_mode), 0o700)

    def test_missing_config_raises_file_not_found(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_config()

    def test_session_round_trip(self) -> None:
        save_session(
            Session(
                cookies={"remix_userid": "1", "remix_userkey": "k"},
                domain="https://z-lib.gd",
                mode="eapi",
            )
        )
        loaded = load_session()
        self.assertEqual(loaded.cookies["remix_userkey"], "k")
        self.assertEqual(loaded.domain, "https://z-lib.gd")
        self.assertEqual(loaded.mode, "eapi")

    def test_kindle_round_trip(self) -> None:
        config = KindleConfig(
            to="reader@kindle.com",
            from_="you@example.com",
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_security="starttls",
        )
        save_kindle(config)
        self.assertEqual(load_kindle(), config)

    def test_weread_round_trip_and_missing_file(self) -> None:
        with self.assertRaises(NotLoggedIn):
            load_weread()
        creds = Credentials(
            vid="1001",
            access_token="token",
            refresh_token="refresh",
            device_id="eink3346912250000000000000000001",
            name="Reader",
        )
        save_weread(creds)
        self.assertEqual(load_weread(), creds)
        self.assertTrue(remove_weread())
        self.assertFalse(remove_weread())
        with self.assertRaises(NotLoggedIn):
            load_weread()

    def test_weread_saver_rejects_a_replaced_login(self) -> None:
        original = Credentials(
            vid="1001",
            access_token="token",
            refresh_token="refresh",
            device_id="eink3346912250000000000000000001",
        )
        save_weread(original)
        saver = weread_saver(original)
        updated = Credentials(
            vid="1001",
            access_token="token2",
            refresh_token="refresh",
            device_id="eink3346912250000000000000000001",
        )
        saver(updated)
        self.assertEqual(load_weread().access_token, "token2")

        save_weread(
            Credentials(
                vid="2002",
                access_token="other",
                refresh_token="other",
                device_id="eink3346912250000000000000000002",
            )
        )
        with self.assertRaises(RuntimeError):
            saver(updated)


if __name__ == "__main__":
    unittest.main()
