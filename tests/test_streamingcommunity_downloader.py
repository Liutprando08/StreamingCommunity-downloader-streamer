# StreamingCommunity resolves its playlist through vixsrc first and only uses
# the vidxgo host as a fallback. These tests pin that order so a future provider
# change cannot silently put the legacy host back in front.

from __future__ import annotations

import unittest
from unittest import mock

# Import the downloader package first: it initializes StreamingCommunity.utils
# before service modules are imported.
from StreamingCommunity.core.downloader import hls as _hls_module  # noqa: F401
from StreamingCommunity.services.streamingcommunity import downloader as sc_downloader


class TestPlaylistProviderOrder(unittest.TestCase):
    def _resolve(self, vixsrc, vidxgo):
        with (
            mock.patch.object(sc_downloader, "_get_vixsrc_playlist_url", **vixsrc),
            mock.patch.object(sc_downloader, "_get_vidxgo_playlist_url", **vidxgo),
        ):
            return sc_downloader._get_playlist_url("tt15398776", False)

    def test_vixsrc_is_used_first(self):
        calls = []

        def vixsrc(*args, **kwargs):
            calls.append("vixsrc")
            return "https://vixsrc.to/playlist/1"

        def vidxgo(*args, **kwargs):
            calls.append("vidxgo")
            return "https://vidxgo.example/playlist/1"

        result = self._resolve(
            {"side_effect": vixsrc},
            {"side_effect": vidxgo},
        )

        self.assertEqual(result, "https://vixsrc.to/playlist/1")
        self.assertEqual(calls, ["vixsrc"])

    def test_falls_back_to_vidxgo_when_vixsrc_returns_none(self):
        calls = []

        def vixsrc(*args, **kwargs):
            calls.append("vixsrc")
            return None

        def vidxgo(*args, **kwargs):
            calls.append("vidxgo")
            return "https://vidxgo.example/playlist/1"

        result = self._resolve(
            {"side_effect": vixsrc},
            {"side_effect": vidxgo},
        )

        self.assertEqual(result, "https://vidxgo.example/playlist/1")
        self.assertEqual(calls, ["vixsrc", "vidxgo"])

    def test_falls_back_to_vidxgo_when_vixsrc_raises(self):
        calls = []

        def vixsrc(*args, **kwargs):
            calls.append("vixsrc")
            raise RuntimeError("vixsrc is down")

        def vidxgo(*args, **kwargs):
            calls.append("vidxgo")
            return "https://vidxgo.example/playlist/1"

        result = self._resolve(
            {"side_effect": vixsrc},
            {"side_effect": vidxgo},
        )

        self.assertEqual(result, "https://vidxgo.example/playlist/1")
        self.assertEqual(calls, ["vixsrc", "vidxgo"])

    def test_returns_none_when_both_providers_fail(self):
        def vixsrc(*args, **kwargs):
            return None

        def vidxgo(*args, **kwargs):
            raise RuntimeError("vidxgo is down")

        result = self._resolve(
            {"side_effect": vixsrc},
            {"side_effect": vidxgo},
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
