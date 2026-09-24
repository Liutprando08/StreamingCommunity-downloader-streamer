import inspect
import time
import unittest
from types import SimpleNamespace

from textual.widgets import OptionList

from StreamingCommunity.cli.tui.app import OsteApp
from StreamingCommunity.cli.tui.parse import parse_ranges
from StreamingCommunity.cli.tui.screens.detail import DetailScreen
from StreamingCommunity.cli.tui.screens.episodes import EpisodesScreen
from StreamingCommunity.cli.tui.screens.queue import QueueScreen
from StreamingCommunity.cli.tui.screens.seasons import SeasonsScreen
from StreamingCommunity.cli.tui.screens.search import SearchScreen
from StreamingCommunity.source.utils.tracker import download_tracker


class FakeEntry:
    def __init__(self, name, type_="film", imdb_id="tt1", year="2020"):
        self.name = name
        self.type = type_
        self.imdb_id = imdb_id
        self.year = year


class FakeProvider:
    name = "Streamingcommunity"
    category = "Film_Serie"

    def __init__(self, delay=0.2):
        self.delay = delay

    def search(self, query):
        return [FakeEntry("Fake Film"), FakeEntry("Fake Serie", type_="tv")]

    def is_series(self, entry):
        return str(getattr(entry, "type", "")).lower() in {
            "tv", "serie", "ova", "ona", "show",
        }

    def new_series_scraper(self, entry):
        return SimpleNamespace(entry=entry)

    def seasons(self, scraper):
        return [SimpleNamespace(number=n, name=f"S{n}") for n in (1, 2, 3)]

    def episodes(self, scraper, season_number):
        return [SimpleNamespace(number=i, name=f"Ep{i}") for i in (1, 2)]

    def _track(self, name, media_type, path):
        from StreamingCommunity.source.utils.tracker import context_tracker

        time.sleep(self.delay)
        did = context_tracker.download_id
        if did:
            download_tracker.start_download(did, name, self.name, media_type)
            download_tracker.update_progress(
                did, "video", 100, "1MB/s", "10MB/20MB", "5/10"
            )
            download_tracker.complete_download(did, success=True, path=path)
        return (path, False)

    def download_film(self, entry):
        return self._track(entry.name, "Film", "/x.mp4")

    def stream_film(self, entry):
        time.sleep(self.delay)
        return None

    def download_episode(self, obj_episode, season, episode, scraper):
        return self._track("ep", "Episode", "/y.mp4")

    def stream_episode(self, obj_episode, season, episode, scraper):
        time.sleep(self.delay)
        return None


async def _settle(pilot, n=10):
    for _ in range(n):
        await pilot.pause()


async def _wait_for(pilot, predicate, limit=80):
    for _ in range(limit):
        await pilot.pause()
        value = predicate()
        if inspect.isawaitable(value):
            value = await value
        if value:
            return value
    raise AssertionError("predicate never became true")


async def _wait_queue_done(pilot):
    seen = False
    for _ in range(200):
        await pilot.pause()
        screen = pilot.app.screen_stack[-1]
        if isinstance(screen, QueueScreen):
            seen = True
            if screen._finished:
                return screen
        elif seen:
            return None
    raise AssertionError("QueueScreen never completed")


def _active(pilot):
    return pilot.app.screen_stack[-1]


class TestParseRanges(unittest.TestCase):
    def test_single(self):
        self.assertEqual(parse_ranges("3", max_count=10), [3])

    def test_range(self):
        self.assertEqual(parse_ranges("2-4", max_count=10), [2, 3, 4])

    def test_mixed(self):
        self.assertEqual(parse_ranges("1,3-4,7", max_count=10), [1, 3, 4, 7])

    def test_star(self):
        self.assertEqual(parse_ranges("*", max_count=4), [1, 2, 3, 4])

    def test_out_of_bounds_ignored(self):
        self.assertEqual(parse_ranges("1,99", max_count=4), [1])

    def test_bad_input(self):
        self.assertEqual(parse_ranges("x", max_count=4), [])


class TestTuiHomeNavigation(unittest.IsolatedAsyncioTestCase):
    async def test_home_to_search(self):
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            _active(pilot).query_one("#menu-list").focus()
            await _settle(pilot)
            await pilot.press("enter")
            await _settle(pilot)
            self.assertIsInstance(_active(pilot), SearchScreen)

    async def test_home_sidebar_has_provider(self):
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            ol = _active(pilot).query_one("#menu-list", OptionList)
            prompts = [
                str(ol.get_option_at_index(i).prompt) for i in range(ol.option_count)
            ]
            self.assertTrue(any("Streamingcommunity" in p for p in prompts))
            self.assertTrue(any("Esci" in p for p in prompts))


class TestTuiFilmFlow(unittest.IsolatedAsyncioTestCase):
    def _detail(self, provider, entry):
        return DetailScreen(provider, entry, is_series=provider.is_series(entry))

    async def test_film_download_queue(self):
        provider = FakeProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            pilot.app.push_screen(self._detail(provider, FakeEntry("Film X")))
            await _settle(pilot)
            await pilot.click("#download-btn")
            await _wait_queue_done(pilot)
            await _settle(pilot)
            self.assertIsInstance(_active(pilot), QueueScreen)
            await pilot.click("#back-btn")
            await _settle(pilot)
            self.assertIsInstance(_active(pilot), DetailScreen)

    async def test_film_stream_queue(self):
        provider = FakeProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            pilot.app.push_screen(self._detail(provider, FakeEntry("Film X")))
            await _settle(pilot)
            await pilot.click("#stream-btn")
            queue = await _wait_queue_done(pilot)
            self.assertTrue(queue._finished)

    async def test_cancel_does_not_crash(self):
        provider = FakeProvider(delay=1.5)
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            pilot.app.push_screen(self._detail(provider, FakeEntry("Film X")))
            await _settle(pilot)
            await pilot.click("#download-btn")
            await _settle(pilot, 5)
            if isinstance(_active(pilot), QueueScreen):
                await pilot.click("#cancel-btn")
                await _settle(pilot, 8)


class TestTuiSeriesFlow(unittest.IsolatedAsyncioTestCase):
    def _detail(self, provider):
        return DetailScreen(
            provider, FakeEntry("Serie Y", type_="tv"), is_series=True
        )

    async def _to_seasons(self, pilot, provider):
        pilot.app.push_screen(self._detail(provider))
        await _settle(pilot)
        await pilot.click("#download-btn")
        await _settle(pilot, 8)

        async def seasons_loaded():
            screen = _active(pilot)
            if isinstance(screen, SeasonsScreen) and screen._scraper is not None:
                return screen
            return None

        return await _wait_for(pilot, seasons_loaded)

    async def _wait_episodes(self, pilot, season=None):
        async def episodes_loaded():
            screen = _active(pilot)
            if isinstance(screen, EpisodesScreen) and screen._episodes:
                if season is not None and screen.season != season:
                    return None
                return screen
            return None

        return await _wait_for(pilot, episodes_loaded)

    async def _enqueue(self, pilot):
        await pilot.click("#select-all")
        await _settle(pilot, 3)
        await pilot.click("#confirm-btn")
        await _wait_queue_done(pilot)

    async def test_single_season_download(self):
        provider = FakeProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            seasons = await self._to_seasons(pilot, provider)
            self.assertIsInstance(seasons, SeasonsScreen)
            self.assertEqual(len(seasons._seasons), 3)
            seasons._apply_ranges("1")
            await _settle(pilot)
            await pilot.click("#confirm-btn")
            episodes = await self._wait_episodes(pilot)
            self.assertIsInstance(episodes, EpisodesScreen)
            await self._enqueue(pilot)
            await _settle(pilot, 20)
            self.assertIsInstance(_active(pilot), SeasonsScreen)

    async def test_multi_season_chain(self):
        provider = FakeProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            seasons = await self._to_seasons(pilot, provider)
            seasons._apply_ranges("1,2")
            await _settle(pilot)
            await pilot.click("#confirm-btn")
            first = await self._wait_episodes(pilot, season=1)
            self.assertEqual(first.season, 1)
            await self._enqueue(pilot)
            second = await self._wait_episodes(pilot, season=2)
            self.assertEqual(second.season, 2)
            await self._enqueue(pilot)
            await _settle(pilot, 20)
            self.assertIsInstance(_active(pilot), SeasonsScreen)

    async def test_series_stream_single_season(self):
        provider = FakeProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            pilot.app.push_screen(self._detail(provider))
            await _settle(pilot)
            await pilot.click("#stream-btn")
            await _settle(pilot, 8)

            async def seasons_loaded():
                screen = _active(pilot)
                if isinstance(screen, SeasonsScreen) and screen._scraper is not None:
                    return screen
                return None

            await _wait_for(pilot, seasons_loaded)
            await pilot.click("#confirm-btn")
            episodes = await self._wait_episodes(pilot)
            self.assertIsInstance(episodes, EpisodesScreen)
            await self._enqueue(pilot)


if __name__ == "__main__":
    unittest.main()