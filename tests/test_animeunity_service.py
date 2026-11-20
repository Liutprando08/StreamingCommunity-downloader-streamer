from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
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


class TestAnimeUnitySearch(unittest.TestCase):
    """The service must use the current JSON endpoints, not the removed ones."""

    def test_title_search_uses_search_and_archive_json_endpoints(self):
        calls: list[tuple[str, dict]] = []

        class FakeResponse:
            def __init__(self, payload: dict):
                self._payload = payload

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return self._payload

        class FakeClient:
            def get(self, url, params=None, cookies=None):
                calls.append((str(url), dict(params or {})))
                if str(url).endswith("/api/search"):
                    return FakeResponse({"data": [{"id": 1}]})
                return FakeResponse({"data": [{"id": 2}]})

        site = SimpleNamespace(
            FULL_URL="https://animeunity.test", SITE_NAME="animeunity"
        )
        with (
            mock.patch.object(animeunity, "site_constants", site),
            mock.patch.object(animeunity, "_ensure_domain", lambda: None),
            mock.patch.object(animeunity, "get_token", return_value={}),
            mock.patch.object(
                animeunity, "create_client_curl", lambda **kwargs: FakeClient()
            ),
            mock.patch.object(animeunity, "process_results") as process,
        ):
            animeunity.title_search("naruto")

        self.assertEqual(
            calls,
            [
                ("https://animeunity.test/api/search", {"q": "naruto"}),
                ("https://animeunity.test/api/archive", {"query": "naruto"}),
            ],
        )
        self.assertEqual(process.call_count, 2)


if __name__ == "__main__":
    unittest.main()
