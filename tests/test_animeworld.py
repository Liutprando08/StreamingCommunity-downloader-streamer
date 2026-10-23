import os
import unittest
from types import SimpleNamespace
from unittest import mock
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import StreamingCommunity.services.animeworld as animeworld_service
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


class FakeAnimeWorldClient:
    info = {
        "tok1": {"grabber": "https://cdn.example/tok1.mp4"},
        "tok2": {"target": "/api/episode/serverPlayerAnimeWorld?id=tok2"},
    }
    source_page = "<video><source src='https://cdn.example/fallback.mp4'></video>"

    def __init__(self, site_url):
        self.site_url = site_url
        self.closed = False

    def get_page(self, url):
        return SimpleNamespace(text=PAGE)

    def absolute_url(self, value):
        if str(value).startswith(("http://", "https://")):
            return str(value)
        return urljoin(f"{self.site_url}/", str(value).lstrip("/"))

    def episode_info(self, token):
        return dict(self.info.get(str(token), {}))

    def player_page(self, target):
        return SimpleNamespace(text=self.source_page)

    def close(self):
        self.closed = True


class TestAnimeWorldScraper(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch(
            "StreamingCommunity.services.animeworld.scrapper.AnimeWorldClient",
            FakeAnimeWorldClient,
        )
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

    def test_resolves_grabber_url(self):
        episode = self.scraper.selectEpisode(1, 0)
        self.assertEqual(
            self.scraper.get_video_url(episode), "https://cdn.example/tok1.mp4"
        )

    def test_resolves_target_fallback_source(self):
        episode = self.scraper.selectEpisode(1, 1)
        self.assertEqual(
            self.scraper.get_video_url(episode),
            "https://cdn.example/fallback.mp4",
        )

    def test_returns_none_without_episode(self):
        self.assertIsNone(self.scraper.get_video_url(None))

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


if __name__ == "__main__":
    unittest.main()


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
