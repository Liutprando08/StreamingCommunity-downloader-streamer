import json
import unittest

from StreamingCommunity.services._base.object import Season
from StreamingCommunity.services.animeunity.scrapper import ScrapeSerieAnime
from StreamingCommunity.services.streamingcommunity.scrapper import (
    GetSerieInfo,
    extract_seasons_from_rsc,
)


def rsc_html(seasons):
    """Build an RSC-styled HTML payload carrying the given seasons."""
    payload = json.dumps({"kind": "series", "seasons": seasons})
    chunk = json.dumps(payload)
    return f'<script>self.__next_f.push([1,{chunk}]);</script>'


class StubEmbed:
    def __init__(self, existing, fail_once=None, raise_once=None):
        self.existing = set(existing)
        self.fail_once = set(fail_once or [])
        self.raise_once = set(raise_once or [])
        self.calls = []

    def __call__(self, season, episode):
        self.calls.append((season, episode))
        key = (season, episode)
        if key in self.raise_once:
            self.raise_once.discard(key)
            raise ConnectionError("boom")
        if key not in self.existing:
            return None
        if key in self.fail_once:
            self.fail_once.discard(key)
            return None
        return {"src": ""}


def make_scraper(stub):
    g = GetSerieInfo("tt0000000", "Test")
    g._get_embed_json = stub
    g.seasons_manager.add(Season(number=1, name="Stagione 1"))
    return g


class TestFillSeasonEpisodes(unittest.TestCase):
    def test_all_episodes_present(self):
        g = make_scraper(StubEmbed(existing=[(1, e) for e in range(1, 21)]))
        eps = g.getEpisodeSeasons(1)
        self.assertEqual([e.number for e in eps], list(range(1, 21)))

    def test_empty_season_early_stop(self):
        stub = StubEmbed(existing=[])
        g = make_scraper(stub)
        eps = g.getEpisodeSeasons(1)
        self.assertEqual(eps, [])
        self.assertLess(len(stub.calls), 40)

    def test_transient_misses_recovered_by_retry(self):
        existing = [(1, e) for e in range(1, 9)]
        stub = StubEmbed(existing=existing, fail_once=existing[2:5])
        g = make_scraper(stub)
        eps = g.getEpisodeSeasons(1)
        self.assertEqual([e.number for e in eps], list(range(1, 9)))

    def test_exceptions_do_not_abort_collection(self):
        existing = [(1, e) for e in range(1, 13)]
        stub = StubEmbed(existing=existing, raise_once=existing[3:6])
        g = make_scraper(stub)
        eps = g.getEpisodeSeasons(1)
        self.assertEqual([e.number for e in eps], list(range(1, 13)))

    def test_partial_window_then_stop(self):
        # episodes 1..10 exist; after 10 the source has a hole for good
        g = make_scraper(StubEmbed(existing=[(1, e) for e in range(1, 11)]))
        eps = g.getEpisodeSeasons(1)
        self.assertEqual([e.number for e in eps], list(range(1, 11)))

    def test_fill_is_idempotent(self):
        g = make_scraper(StubEmbed(existing=[(1, e) for e in range(1, 9)]))
        self.assertEqual(len(g.getEpisodeSeasons(1)), 8)
        self.assertEqual(len(g.getEpisodeSeasons(1)), 8)


class TestGetNumberSeason(unittest.TestCase):
    def test_returns_real_count(self):
        stub = StubEmbed(existing=[(1, 1), (2, 1)])
        g = GetSerieInfo("tt0000000", "Test")
        g._get_embed_json = stub
        self.assertEqual(g.getNumberSeason(), 2)

    def test_empty_series(self):
        stub = StubEmbed(existing=[])
        g = GetSerieInfo("tt0000000", "Test")
        g._get_embed_json = stub
        self.assertEqual(g.getNumberSeason(), 0)


class TestExtractSeasonsFromRSC(unittest.TestCase):
    def test_returns_parsed_seasons(self):
        seasons = [
            {
                "number": 1,
                "name": "Stagione 1",
                "episodes": [
                    {"number": 1, "title": "Pilota"},
                    {"number": 2, "title": "Biscotti"},
                ],
            },
            {"number": 2, "name": "Stagione 2", "episodes": []},
        ]
        parsed = extract_seasons_from_rsc(rsc_html(seasons))
        self.assertEqual([s["number"] for s in parsed], [1, 2])
        self.assertEqual(parsed[0]["episodes"][0]["title"], "Pilota")

    def test_no_rsc_payload_returns_empty(self):
        self.assertEqual(extract_seasons_from_rsc("<html></html>"), [])


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class FakeClient:
    def __init__(self, text):
        self._text = text

    def get(self, url):
        return FakeResponse(self._text)


class TestTitlePageScraping(unittest.TestCase):
    def make_fixture(self):
        seasons = [
            {
                "number": 1,
                "name": "Stagione 1",
                "episodes": [
                    {"number": 1, "title": "Pilota"},
                    {"number": 2, "title": "Biscotti"},
                ],
            },
            {"number": 2, "name": "Stagione 2", "episodes": []},
        ]
        g = GetSerieInfo("tt0000000", "Test", url="https://example.invalid/sc")
        g._client = FakeClient(rsc_html(seasons))
        return g

    def test_getNumberSeason_from_title_page(self):
        g = self.make_fixture()
        self.assertEqual(g.getNumberSeason(), 2)

    def test_getEpisodeSeasons_from_title_page(self):
        g = self.make_fixture()
        eps = g.getEpisodeSeasons(1)
        self.assertEqual([e.number for e in eps], [1, 2])
        self.assertEqual(eps[0].name, "Pilota")

    def test_getNumberSeason_idempotent(self):
        g = self.make_fixture()
        self.assertEqual(g.getNumberSeason(), 2)
        self.assertEqual(g.getNumberSeason(), 2)


class FakeAnimeScraper(ScrapeSerieAnime):
    """AnimeUnity scraper with the HTTP layer replaced by a static payload."""

    def __init__(self, episodes=None):
        super().__init__("https://example.invalid")
        self.setup(None, 1, "Test Anime")
        self._payload = episodes or []
        self.season_requests = []

    def _fetch_all_episodes(self, season_number=1):
        self.season_requests.append(season_number)
        self._episodes_by_season[season_number] = self._payload
        if season_number == 1 or self.episodes_cache is None:
            self.episodes_cache = self._payload


def _raw(count):
    return [{"id": 100 + n, "number": n, "title": f"Ep {n}"} for n in range(1, count + 1)]


class TestAnimeUnityScraper(unittest.TestCase):
    def test_getNumberSeason_registers_single_season(self):
        s = FakeAnimeScraper(_raw(3))
        self.assertEqual(s.getNumberSeason(), 1)
        self.assertEqual([x.number for x in s.seasons_manager.seasons], [1])
        # idempotent: does not append a second season
        s.getNumberSeason()
        self.assertEqual(len(s.seasons_manager.seasons), 1)

    def test_getEpisodeSeasons_returns_all_episodes(self):
        s = FakeAnimeScraper(_raw(5))
        self.assertEqual([e.number for e in s.getEpisodeSeasons(1)], [1, 2, 3, 4, 5])

    def test_episode_names_come_from_payload(self):
        s = FakeAnimeScraper(_raw(1))
        self.assertEqual(s.getEpisodeSeasons(1)[0].name, "Ep 1")

    def test_episode_name_falls_back_to_number(self):
        s = FakeAnimeScraper([{"id": 7, "number": 3}])
        self.assertEqual(s.getEpisodeSeasons(1)[0].name, "Episode 3")

    def test_get_count_episodes(self):
        self.assertEqual(FakeAnimeScraper(_raw(12)).get_count_episodes(), 12)

    def test_get_count_episodes_returns_none_on_failure(self):
        class Broken(FakeAnimeScraper):
            def _fetch_all_episodes(self, season_number=1):
                self._episodes_by_season[season_number] = None

        self.assertIsNone(Broken().get_count_episodes())

    def test_getEpisodeSeasons_is_idempotent_and_caches(self):
        s = FakeAnimeScraper(_raw(4))
        first = s.getEpisodeSeasons(1)
        second = s.getEpisodeSeasons(1)
        self.assertEqual(len(first), len(second))
        self.assertEqual(s.season_requests, [1])

    def test_selectEpisode_uses_season_and_index(self):
        s = FakeAnimeScraper(_raw(3))
        ep = s.selectEpisode(1, 2)
        self.assertEqual(ep.number, 3)
        self.assertIsNone(s.selectEpisode(1, 99))

    def test_setup_without_name_leaves_series_name_defined(self):
        s = FakeAnimeScraper()
        s.setup(None, 1, None)
        self.assertEqual(s.series_name, "")
        self.assertFalse(s.is_series)


if __name__ == "__main__":
    unittest.main()