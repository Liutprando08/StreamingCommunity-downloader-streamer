import os
import unittest
from types import SimpleNamespace
from unittest import mock

from bs4 import BeautifulSoup

import StreamingCommunity.services.animeworld as animeworld_service
from StreamingCommunity.player.sweetpixel import VideoSource
from StreamingCommunity.services.animeworld import _build_entry, _status_type
from StreamingCommunity.services.animeworld.scrapper import ScrapSerie


PAGE = """
<html>
  <head><meta name="description" content="A test synopsis"></head>
  <body>
    <h1 id="anime-title">Test &amp; Show</h1>
    <div id="player" data-anime-id="42"></div>
    <ul>
      <li class="episode">
        <a data-id="tok2" data-episode-id="102" data-episode-num="2"
           href="/play/test.abc/tok2">Ep 2</a>
      </li>
      <li class="episode">
        <a data-id="tok1" data-episode-id="101" data-episode-num="1"
           href="/play/test.abc/tok1">Ep 1</a>
      </li>
      <li class="episode">
        <a data-id="tok2" data-episode-id="102" data-episode-num="2"
           href="/play/test.abc/tok2">Duplicate</a>
      </li>
    </ul>
  </body>
</html>
"""


class _FakeResponse:
    def __init__(self, content=b"", text=None, json_data=None):
        self.content = content
        self.text = text if text is not None else content.decode("utf-8", errors="replace")
        self._json = json_data

    def raise_for_status(self):
        return None

    def json(self):
        return self._json


class _FakeScraperClient:
    """Minimal http client used by ScrapSerie to load the anime page."""

    def __init__(self, page):
        self.page = page
        self.closed = False
        self.requests = []

    def get(self, url, **kwargs):
        self.requests.append(url)
        return _FakeResponse(content=self.page.encode("utf-8"))

    def close(self):
        self.closed = True


class TestAnimeWorldScraper(unittest.TestCase):
    def setUp(self):
        self.client = _FakeScraperClient(PAGE)
        patchers = [
            mock.patch(
                "StreamingCommunity.services.animeworld.scrapper.get_session_and_csrf",
                return_value=("session-id", "csrf-token"),
            ),
            mock.patch(
                "StreamingCommunity.services.animeworld.scrapper.create_client",
                return_value=self.client,
            ),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        self.scraper = ScrapSerie("/play/test.abc", site_url="https://aw.test")

    def test_parses_and_sorts_episodes(self):
        episodes = self.scraper.get_episodes()
        self.assertEqual([e.number for e in episodes], ["1", "2"])
        self.assertEqual([e.token for e in episodes], ["tok1", "tok2"])
        self.assertEqual(len(self.scraper.get_episodes()), 2)
        self.assertEqual(self.scraper.get_count_episodes(), 2)

    def test_registers_single_season(self):
        self.assertEqual(self.scraper.getNumberSeason(), 1)
        self.assertEqual(len(self.scraper.seasons_manager), 1)
        season = self.scraper.seasons_manager.seasons[0]
        self.assertEqual(season.number, 1)
        self.assertEqual(season.id, "42")

    def test_selects_episode_by_index(self):
        self.assertEqual(self.scraper.selectEpisode(1, 0).number, "1")
        self.assertEqual(self.scraper.selectEpisode(1, 1).number, "2")
        self.assertIsNone(self.scraper.selectEpisode(1, 99))

    def test_series_name_and_description(self):
        self.assertIn("Test", self.scraper.get_name())
        self.assertEqual(self.scraper.get_description(), "A test synopsis")

    def test_falls_back_to_href_token_and_anchor_text(self):
        self.scraper.soup = BeautifulSoup(
            """
            <ul>
              <li class="episode">
                <a href="/play/test.abc/legacy-token">Episodio 9</a>
              </li>
            </ul>
            """,
            "html.parser",
        )
        self.scraper._episodes = None

        episodes = self.scraper.get_episodes()
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0].number, "9")
        self.assertEqual(episodes[0].token, "legacy-token")
        self.assertEqual(episodes[0].name, "Episodio 9")


class _FakeVideoApiClient:
    """Fake client for the episode-info endpoint and the player page."""

    def __init__(self, info, source_page):
        self.info = info
        self.source_page = source_page
        self.closed = False

    def get(self, url, **kwargs):
        if "/api/episode/info" in url:
            return _FakeResponse(json_data=self.info)
        return _FakeResponse(content=self.source_page.encode("utf-8"))

    def close(self):
        self.closed = True


class TestAnimeWorldVideoSource(unittest.TestCase):
    """The mp4 URL resolution now lives in player.sweetpixel.VideoSource."""

    source_page = "<video><source src='https://cdn.example/fallback.mp4'></video>"

    def _resolve(self, info):
        client = _FakeVideoApiClient(info, self.source_page)
        with mock.patch(
            "StreamingCommunity.player.sweetpixel.create_client", return_value=client
        ), mock.patch(
            "StreamingCommunity.player.sweetpixel.get_headers", return_value={}
        ):
            return VideoSource(
                "https://aw.test",
                SimpleNamespace(id="tok1"),
                "session-id",
                "csrf-token",
            ).get_playlist()

    def test_prefers_grabber_url(self):
        self.assertEqual(
            self._resolve({"grabber": "https://cdn.example/tok1.mp4"}),
            "https://cdn.example/tok1.mp4",
        )

    def test_uses_download_url_fallback(self):
        self.assertEqual(
            self._resolve({"download": "https://cdn.example/download.mp4"}),
            "https://cdn.example/download.mp4",
        )

    def test_resolves_target_page_source(self):
        self.assertEqual(
            self._resolve({"target": "/api/episode/serverPlayerAnimeWorld?id=tok2"}),
            "https://cdn.example/fallback.mp4",
        )

    def test_returns_none_when_no_source_found(self):
        self.assertIsNone(self._resolve({}))


class TestAnimeWorldSearchMapping(unittest.TestCase):
    def _status(self, markup):
        return BeautifulSoup(markup, "html.parser").find("div", class_="status")

    def test_status_types(self):
        cases = {
            "movie": "Movie",
            "ova": "OVA",
            "ona": "ONA",
            "special": "ONA",
            "tv": "TV",
        }
        for css, expected in cases.items():
            media_type, _, _ = _status_type(
                self._status(f'<div class="status"><div class="{css}">x</div></div>')
            )
            self.assertEqual(media_type, expected, css)

    def test_dub_and_special_flags(self):
        media_type, dubbed, special = _status_type(
            self._status(
                '<div class="status"><div class="dub">ITA</div>'
                '<div class="special">SP</div></div>'
            )
        )
        self.assertEqual(media_type, "ONA")
        self.assertTrue(dubbed)
        self.assertTrue(special)

    def test_build_entry(self):
        card = BeautifulSoup(
            '<a class="poster" href="/play/test.abc" data-tip="api/tooltip/7">'
            '<img src="/img.jpg" alt="Test Show">'
            '<div class="status"><div class="dub">ITA</div></div>'
            "</a>",
            "html.parser",
        ).find("a")
        entry = _build_entry(card)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.name, "Test Show")
        self.assertEqual(entry.type, "TV")
        self.assertEqual(entry.provider_language, "ITA")
        self.assertTrue(entry.dub)
        self.assertEqual(entry.slug, "/play/test.abc")
        self.assertEqual(entry.id, "7")
        self.assertTrue(entry.url.endswith("/play/test.abc"))
        self.assertTrue(entry._tip_url.endswith("/api/tooltip/7"))


class TestAnimeWorldCliRouting(unittest.TestCase):
    def test_streaming_mode_uses_stream_functions(self):
        with mock.patch.dict(os.environ, {"STREAMING_MODE": "1"}):
            with mock.patch.object(animeworld_service, "base_process_search_result") as base:
                animeworld_service.process_search_result(SimpleNamespace())
        kwargs = base.call_args.kwargs
        self.assertIs(kwargs["download_film_func"], animeworld_service.stream_film)
        self.assertIs(kwargs["download_series_func"], animeworld_service.stream_series)

    def test_download_mode_uses_download_functions(self):
        with mock.patch.dict(os.environ, {"STREAMING_MODE": "0"}):
            with mock.patch.object(animeworld_service, "base_process_search_result") as base:
                animeworld_service.process_search_result(SimpleNamespace())
        kwargs = base.call_args.kwargs
        self.assertIs(kwargs["download_film_func"], animeworld_service.download_film)
        self.assertIs(kwargs["download_series_func"], animeworld_service.download_series)


if __name__ == "__main__":
    unittest.main()
