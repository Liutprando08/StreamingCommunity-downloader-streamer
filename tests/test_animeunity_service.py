from __future__ import annotations

import os
import unittest
from unittest import mock

import StreamingCommunity.services.animeunity as animeunity


class TestAnimeUnityStreamingMode(unittest.TestCase):
    """``--stream`` sets STREAMING_MODE=1; the service must honour it."""

    def _capture(self, streaming: bool) -> dict:
        captured: dict = {}

        def fake_base(**kwargs):
            captured.update(kwargs)
            return True

        with mock.patch.object(animeunity, "base_process_search_result", fake_base):
            with mock.patch.dict(os.environ, {}, clear=False):
                if streaming:
                    os.environ["STREAMING_MODE"] = "1"
                else:
                    os.environ.pop("STREAMING_MODE", None)
                animeunity.process_search_result(object())

        return captured

    def test_streaming_mode_uses_stream_functions(self):
        captured = self._capture(streaming=True)

        self.assertIs(captured["download_film_func"], animeunity.stream_film)
        self.assertIs(captured["download_series_func"], animeunity.stream_series)

    def test_default_mode_uses_download_functions(self):
        captured = self._capture(streaming=False)

        self.assertIs(captured["download_film_func"], animeunity.download_film)
        self.assertIs(captured["download_series_func"], animeunity.download_series)

    def test_other_env_values_keep_download_mode(self):
        captured: dict = {}

        def fake_base(**kwargs):
            captured.update(kwargs)
            return True

        with mock.patch.object(animeunity, "base_process_search_result", fake_base):
            with mock.patch.dict(os.environ, {"STREAMING_MODE": "0"}, clear=False):
                animeunity.process_search_result(object())

        self.assertIs(captured["download_film_func"], animeunity.download_film)
        self.assertIs(captured["download_series_func"], animeunity.download_series)


if __name__ == "__main__":
    unittest.main()
