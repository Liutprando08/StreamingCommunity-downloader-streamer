"""Tests for the Android/mobile headless layer (no network required)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from StreamingCommunity.mobile import bootstrap

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestBootstrap(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._saved = {
            key: os.environ.get(key)
            for key in (bootstrap.HOME_ENV, bootstrap.OUTPUT_ENV)
        }

    def tearDown(self):
        os.chdir(self._cwd)
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_prepare_creates_home_and_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = bootstrap.prepare(tmp)

            self.assertEqual(paths["home"], os.path.abspath(tmp))
            self.assertEqual(paths["output"], os.path.join(os.path.abspath(tmp), "Video"))
            self.assertTrue(os.path.isdir(paths["output"]))
            self.assertTrue(os.path.isdir(paths["conf"]))
            self.assertEqual(os.environ[bootstrap.HOME_ENV], paths["home"])
            self.assertEqual(os.environ[bootstrap.OUTPUT_ENV], paths["output"])
            self.assertEqual(os.getcwd(), paths["home"])

    def test_prepare_honours_explicit_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "custom")
            paths = bootstrap.prepare(tmp, output_root=output)
            self.assertEqual(paths["output"], os.path.abspath(output))
            self.assertTrue(os.path.isdir(output))

    def test_android_detection(self):
        saved = os.environ.get("ANDROID_ARGUMENT")
        os.environ["ANDROID_ARGUMENT"] = "/data"
        try:
            self.assertTrue(bootstrap.is_android())
        finally:
            if saved is None:
                os.environ.pop("ANDROID_ARGUMENT", None)
            else:
                os.environ["ANDROID_ARGUMENT"] = saved


class TestMobileApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Point the config at the repository copy so no download is attempted.
        os.environ[bootstrap.HOME_ENV] = str(REPO_ROOT)
        os.environ[bootstrap.OUTPUT_ENV] = str(REPO_ROOT / "Video")
        from StreamingCommunity.mobile import api

        cls.api = api

    @classmethod
    def tearDownClass(cls):
        os.environ.pop(bootstrap.HOME_ENV, None)
        os.environ.pop(bootstrap.OUTPUT_ENV, None)

    def test_supported_services(self):
        services = {item["id"] for item in self.api.list_services()}
        self.assertEqual(services, {"streamingcommunity", "altadefinizione"})

    def test_entry_roundtrip(self):
        payload = {
            "id": 1,
            "name": "Example",
            "type": "tv",
            "year": "2024",
            "url": "https://example.test/titles/1-example",
            "imdb_id": "tt1234567",
            "slug": "example",
            "desc": "A description",
            "score": "8.0",
        }
        entry = self.api._entry_from_payload(payload)
        self.assertEqual(entry.name, "Example")
        self.assertEqual(entry.type, "tv")
        self.assertEqual(self.api._entry_payload(entry), payload)

    def test_unknown_service_raises(self):
        with self.assertRaises(self.api.MobileError):
            self.api._load("not-a-service")

    def test_empty_search_returns_empty(self):
        self.assertEqual(self.api.search("streamingcommunity", "   "), [])


if __name__ == "__main__":
    unittest.main()
