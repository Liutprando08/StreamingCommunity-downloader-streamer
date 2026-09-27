import unittest

from StreamingCommunity.services._base.object import Season
from StreamingCommunity.services.streamingcommunity.scrapper import GetSerieInfo


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


if __name__ == "__main__":
    unittest.main()