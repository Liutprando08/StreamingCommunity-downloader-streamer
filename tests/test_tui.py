import inspect
import time
import unittest
from types import SimpleNamespace

from textual.widgets import DataTable, Input, OptionList, Select

import StreamingCommunity.cli.tui.providers.torrent
import StreamingCommunity.services.torrent.downloader
from StreamingCommunity.cli.tui.app import OsteApp
from StreamingCommunity.cli.tui.parse import parse_ranges
from StreamingCommunity.cli.tui.providers import registry
from StreamingCommunity.cli.tui.providers.animeunity import AnimeunityProvider
from StreamingCommunity.cli.tui.screens.detail import DetailScreen
from StreamingCommunity.cli.tui.screens.episodes import EpisodesScreen
from StreamingCommunity.cli.tui.screens.home import HomeScreen
from StreamingCommunity.cli.tui.screens.music import (
    LEVEL_RESULTS,
    LEVEL_SEARCH,
    LEVEL_TRACKS,
    MusicScreen,
)
from StreamingCommunity.cli.tui.screens.queue import QueueScreen
from StreamingCommunity.cli.tui.screens.seasons import SeasonsScreen
from StreamingCommunity.cli.tui.screens.search import SearchScreen
from StreamingCommunity.source.utils.tracker import download_tracker


class FakeEntry:
    def __init__(self, name, type_="film", imdb_id="tt1", year="2020", **extra):
        self.name = name
        self.type = type_
        self.imdb_id = imdb_id
        self.year = year
        for key, value in extra.items():
            setattr(self, key, value)


class FakeProvider:
    name = "Streamingcommunity"
    category = "Film_Serie"
    alias = "streamingcommunity"

    flow = "episode"
    supports_streaming = True
    supports_seasons = True

    def __init__(self, delay=0.2):
        self.delay = delay

    def result_columns(self):
        return (("Nome", "name"), ("Tipo", "type"), ("Anno", "year"), ("ID", "imdb_id"))

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


class FakeMusicProvider:
    """Mirrors the contract of the real music providers."""

    name = "Fakemp3"
    category = "Music"
    alias = "fakemp3"

    flow = "music"
    supports_streaming = False
    supports_seasons = False

    _ALBUM = FakeEntry("Fake Album", type_="Album", artist="Fake Artist")
    _SONG = FakeEntry("Fake Song", type_="Song", artist="Fake Artist")
    _TRACKS = [
        FakeEntry(f"Track {n}", type_="Song", artist="Fake Artist")
        for n in range(1, 4)
    ]

    def __init__(self, delay=0.2):
        self.delay = delay
        self.downloaded = []

    def search_modes(self):
        return ("Song", "Album", "Artist")

    def result_columns(self):
        return (
            ("Nome", "name"),
            ("Tipo", "type"),
            ("Artista", "artist"),
            ("Album", "album"),
        )

    def search(self, query, mode):
        if mode == "Song":
            return [self._SONG]
        if mode == "Album":
            return [self._ALBUM]
        return [FakeEntry("Fake Artist", type_="Artist")]

    def albums(self, entry):
        return [self._ALBUM]

    def tracks(self, entry):
        return list(self._TRACKS)

    def drilldown(self, entry):
        media_type = str(getattr(entry, "type", "")).lower()
        if media_type == "artist":
            return "albums", self.albums(entry)
        if media_type == "album":
            return "tracks", self.tracks(entry)
        return None

    def _track(self, name):
        from StreamingCommunity.source.utils.tracker import context_tracker

        time.sleep(self.delay)
        self.downloaded.append(name)
        did = context_tracker.download_id
        if did:
            download_tracker.start_download(did, name, self.name, "Track")
            download_tracker.update_progress(did, "audio", 100, "1MB/s", "3MB/3MB")
            download_tracker.complete_download(did, success=True, path="/t.mp3")
        return "/t.mp3"

    def download_track(self, entry):
        return self._track(entry.name)

    def download_album(self, entry):
        return self._track(entry.name)


class FakeTorrentProvider:
    """Mirrors the contract of the real torrent provider."""

    name = "Torrent"
    category = "Film_Serie"
    alias = "torrent"

    flow = "atomic"
    supports_streaming = False
    supports_seasons = False

    def __init__(self, delay=0.2):
        self.delay = delay
        self.calls = []

    def search(self, query):
        return [
            FakeEntry("Movie 2020", type_="film", quality="1080p", size="1.2 GB", seeders=90),
            FakeEntry("Show S01", type_="tv", quality="720p", size="4.0 GB", seeders=40),
        ]

    def result_columns(self):
        return (
            ("Nome", "name"),
            ("Tipo", "type"),
            ("Anno", "year"),
            ("Qualità", "quality"),
            ("Dim.", "size"),
            ("Seed", "seeders"),
        )

    def is_series(self, entry):
        return str(getattr(entry, "type", "")).lower() in {"tv"}

    def _track(self, name):
        from StreamingCommunity.source.utils.tracker import context_tracker

        time.sleep(self.delay)
        self.calls.append(name)
        did = context_tracker.download_id
        if did:
            download_tracker.start_download(did, name, self.name, "Film")
            download_tracker.update_progress(did, "video", 100, "1MB/s", "1GB/1GB")
            download_tracker.complete_download(did, success=True, path="/t.mkv")
        return "/t.mkv"

    def download_film(self, entry):
        return self._track(entry.name)


async def _settle(pilot, n=10):
    for _ in range(n):
        await pilot.pause()


async def _wait_for(pilot, predicate, limit=150, delay=0.05):
    for _ in range(limit):
        await pilot.pause(delay)
        value = predicate()
        if inspect.isawaitable(value):
            value = await value
        if value:
            return value
    raise AssertionError("predicate never became true")


async def _wait_queue_done(pilot):
    seen = False
    for _ in range(400):
        await pilot.pause(0.05)
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

    async def test_home_sidebar_has_animeunity(self):
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            ol = _active(pilot).query_one("#menu-list", OptionList)
            prompts = [
                str(ol.get_option_at_index(i).prompt) for i in range(ol.option_count)
            ]
            self.assertTrue(any("Animeunity (Anime)" in p for p in prompts))

    async def test_home_selects_animeunity_search(self):
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            index = next(
                i
                for i, p in enumerate(registry.all())
                if p.name == "Animeunity"
            )
            _active(pilot).query_one("#menu-list").focus()
            await _settle(pilot)
            _active(pilot).query_one("#menu-list", OptionList).highlighted = index
            await _settle(pilot)
            await pilot.press("enter")
            await _settle(pilot)
            screen = _active(pilot)
            self.assertIsInstance(screen, SearchScreen)
            self.assertEqual(screen.provider.name, "Animeunity")

    async def test_home_exit_option(self):
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            ol = _active(pilot).query_one("#menu-list", OptionList)
            ol.focus()
            await _settle(pilot)
            ol.highlighted = len(registry.all())
            await _settle(pilot)
            await pilot.press("enter")
            await _settle(pilot)
            self.assertIsInstance(_active(pilot), HomeScreen)


class TestAnimeunityProvider(unittest.TestCase):
    def setUp(self):
        self.provider = AnimeunityProvider()

    def test_registry_lookup(self):
        found = registry.get("animeunity")
        self.assertIsInstance(found, AnimeunityProvider)
        self.assertEqual(found.name, "Animeunity")
        self.assertEqual(found.category, "Anime")
        self.assertIsNone(registry.get("does-not-exist"))

    def test_implements_service_provider_protocol(self):
        required = (
            "search",
            "is_series",
            "new_series_scraper",
            "seasons",
            "episodes",
            "download_film",
            "stream_film",
            "download_episode",
            "stream_episode",
        )
        for attr in required:
            self.assertTrue(callable(getattr(self.provider, attr, None)), attr)

    def test_film_types_are_not_series(self):
        for media_type in ("film", "movie", "Movie", "FILM"):
            entry = FakeEntry("X", type_=media_type)
            self.assertFalse(self.provider.is_series(entry), media_type)

    def test_unknown_types_are_treated_as_series(self):
        for media_type in ("anime", "tv", "serie", "ova", "show", "", None):
            entry = FakeEntry("X", type_=media_type)
            self.assertTrue(self.provider.is_series(entry), media_type)

    def test_seasons_and_episodes_delegate_to_scraper(self):
        scraper = SimpleNamespace(
            seasons_manager=SimpleNamespace(
                seasons=[SimpleNamespace(number=1, name="S1")]
            ),
            getNumberSeason=lambda: 1,
            getEpisodeSeasons=lambda s: [SimpleNamespace(number=1, name="Ep1")],
        )
        self.assertEqual(self.provider.seasons(scraper)[0].number, 1)
        self.assertEqual(self.provider.episodes(scraper, 1)[0].name, "Ep1")


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


class TestMusicProviders(unittest.TestCase):
    def test_registry_lookup(self):
        self.assertEqual(registry.get("musicmp3").name, "Musicmp3")
        self.assertEqual(registry.get("goldenmp3").name, "Goldenmp3")
        self.assertIsNone(registry.get("does-not-exist"))

    def test_flow_and_flags(self):
        for alias in ("musicmp3", "goldenmp3"):
            provider = registry.get(alias)
            self.assertEqual(provider.flow, "music", alias)
            self.assertEqual(provider.category, "Music", alias)
            self.assertFalse(provider.supports_streaming, alias)
            self.assertFalse(provider.supports_seasons, alias)

    def test_by_flow_isolation(self):
        self.assertEqual([p.name for p in registry.by_flow("episode")],
                         ["Streamingcommunity", "Animeunity"])
        self.assertEqual([p.name for p in registry.by_flow("atomic")], ["Torrent"])
        self.assertEqual([p.name for p in registry.by_flow("music")],
                         ["Musicmp3", "Goldenmp3"])

    def test_search_modes(self):
        self.assertEqual(registry.get("musicmp3").search_modes(),
                         ("Song", "Album", "Artist"))
        # Goldenmp3 only ships albums.
        self.assertEqual(registry.get("goldenmp3").search_modes(), ("Album",))

    def test_music_columns_cover_track_metadata(self):
        columns = dict(registry.get("musicmp3").result_columns())
        self.assertIn("name", columns.values())
        self.assertIn("artist", columns.values())
        self.assertIn("album", columns.values())

    def test_implements_music_protocol(self):
        provider = registry.get("musicmp3")
        for attr in ("search_modes", "result_columns", "search", "drilldown",
                     "download_track", "download_album"):
            self.assertTrue(callable(getattr(provider, attr, None)), attr)

    def test_download_track_sanitizes_title(self):
        """download_track receives a title, not a numeric id."""
        captured = {}

        class _Downloader:
            @staticmethod
            def download_track(entry):
                captured["title"] = entry.name
                return "/t.mp3"

        provider = registry.get("musicmp3")
        entry = FakeEntry("Track 1", type_="Song", artist="Fake Artist")
        provider._downloader = lambda: _Downloader
        provider.download_track(entry)
        self.assertEqual(captured["title"], "Track 1")

    def test_fake_drilldown_routing(self):
        provider = FakeMusicProvider()
        artist = FakeEntry("A", type_="Artist")
        album = FakeMusicProvider._ALBUM
        song = FakeMusicProvider._SONG
        self.assertEqual(provider.drilldown(artist)[0], "albums")
        self.assertEqual(provider.drilldown(album)[0], "tracks")
        self.assertIsNone(provider.drilldown(song))


class TestTorrentProviders(unittest.TestCase):
    def setUp(self):
        self.provider = registry.get("torrent")

    def test_registry_and_flow(self):
        self.assertEqual(self.provider.name, "Torrent")
        self.assertEqual(self.provider.category, "Film_Serie")
        self.assertEqual(self.provider.flow, "atomic")
        self.assertFalse(self.provider.supports_streaming)
        self.assertFalse(self.provider.supports_seasons)

    def test_result_columns_expose_torrent_metadata(self):
        columns = [header for header, _attr in self.provider.result_columns()]
        self.assertEqual(columns[0], "Nome")
        lowered = {c.lower() for c in columns}
        self.assertTrue({"qualità", "dim.", "seed", "fonte"} & lowered)

    def test_is_series(self):
        self.assertFalse(self.provider.is_series(FakeEntry("Movie", type_="film")))
        self.assertTrue(self.provider.is_series(FakeEntry("Show", type_="tv")))

    def test_prompt_dub_is_never_interactive(self):
        """prompt_audio_dub() blocks on stdin, so the TUI must disable it."""
        source = inspect.getsource(
            StreamingCommunity.cli.tui.providers.torrent.TorrentProvider
        )
        self.assertIn("prompt_dub=False", source)
        self.assertNotIn("prompt_dub=True", source)

    def test_prompt_dub_optional_on_downloader(self):
        for fn in (
            StreamingCommunity.services.torrent.downloader.download_film,
            StreamingCommunity.services.torrent.downloader.download_series,
        ):
            self.assertIn("prompt_dub", inspect.signature(fn).parameters)

    def test_download_film_routes_by_type(self):
        provider = FakeTorrentProvider()
        movie = FakeEntry("Movie", type_="film")
        show = FakeEntry("Show", type_="tv")
        provider.download_film(movie)
        provider.download_film(show)
        self.assertEqual(provider.calls, ["Movie", "Show"])


class TestTuiMusicFlow(unittest.IsolatedAsyncioTestCase):
    async def _open(self, pilot, provider):
        pilot.app.push_screen(MusicScreen(provider))
        await _settle(pilot)
        return _active(pilot)

    async def _search(self, pilot, screen, mode, query="fake"):
        select = screen.query_one("#music-mode", Select)
        select.value = mode
        await _settle(pilot)
        field = screen.query_one("#music-query", Input)
        field.value = query
        field.focus()
        await _settle(pilot)
        await pilot.press("enter")

        async def loaded(level):
            def predicate():
                active = _active(pilot)
                if isinstance(active, MusicScreen) and active._level == level:
                    return active
                return None

            return await _wait_for(pilot, predicate)

        return await loaded(LEVEL_RESULTS)

    async def test_search_screen_redirects_music_providers(self):
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            pilot.app.push_screen(SearchScreen(FakeMusicProvider()))
            await _settle(pilot)
            self.assertIsInstance(_active(pilot), MusicScreen)

    async def test_starts_on_search_level(self):
        provider = FakeMusicProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            screen = await self._open(pilot, provider)
            self.assertEqual(screen._level, LEVEL_SEARCH)

    async def test_album_descends_to_tracks(self):
        provider = FakeMusicProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            screen = await self._open(pilot, provider)
            results = await self._search(pilot, screen, "Album")
            self.assertEqual(len(results._entries), 1)
            table = results.query_one("#music-table", DataTable)
            table.focus()
            await _settle(pilot)
            await pilot.press("enter")
            screen = await _wait_for(
                pilot,
                lambda: _active(pilot)
                if isinstance(_active(pilot), MusicScreen)
                and _active(pilot)._level == LEVEL_TRACKS
                else None,
            )
            self.assertEqual(len(screen._entries), 3)
            # Back returns to the search results.
            screen.action_back()
            await _settle(pilot)
            self.assertEqual(_active(pilot)._level, LEVEL_RESULTS)

    async def test_song_enqueues_directly(self):
        provider = FakeMusicProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            screen = await self._open(pilot, provider)
            results = await self._search(pilot, screen, "Song")
            table = results.query_one("#music-table", DataTable)
            table.focus()
            await _settle(pilot)
            await pilot.press("enter")
            queue = await _wait_queue_done(pilot)
            self.assertIsInstance(queue, QueueScreen)
            self.assertEqual(provider.downloaded, ["Fake Song"])

    async def test_select_all_tracks_enqueues_queue(self):
        provider = FakeMusicProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            screen = await self._open(pilot, provider)
            results = await self._search(pilot, screen, "Album")
            results.query_one("#music-table", DataTable).focus()
            await _settle(pilot)
            await pilot.press("enter")
            await _wait_for(
                pilot,
                lambda: _active(pilot)
                if isinstance(_active(pilot), MusicScreen)
                and _active(pilot)._level == LEVEL_TRACKS
                else None,
            )
            await pilot.click("#select-all")
            await _settle(pilot, 3)
            await pilot.click("#confirm-btn")
            await _wait_queue_done(pilot)
            self.assertEqual(provider.downloaded, ["Track 1", "Track 2", "Track 3"])

    async def test_selection_marks_rows(self):
        provider = FakeMusicProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            screen = await self._open(pilot, provider)
            results = await self._search(pilot, screen, "Album")
            results.query_one("#music-table", DataTable).focus()
            await _settle(pilot)
            await pilot.press("enter")
            tracks = await _wait_for(
                pilot,
                lambda: _active(pilot)
                if isinstance(_active(pilot), MusicScreen)
                and _active(pilot)._level == LEVEL_TRACKS
                else None,
            )
            tracks._toggle(1)
            await _settle(pilot)
            table = tracks.query_one("#music-table", DataTable)
            self.assertEqual(
                table.get_row("1")[0], "\u2713", "row 1 should be marked selected"
            )
            self.assertEqual(table.get_row("0")[0], " ")


class TestTuiTorrentFlow(unittest.IsolatedAsyncioTestCase):
    def _detail(self, provider, entry):
        return DetailScreen(provider, entry, is_series=provider.is_series(entry))

    async def test_movie_downloads_as_single_torrent(self):
        provider = FakeTorrentProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            entry = provider.search("x")[0]
            pilot.app.push_screen(self._detail(provider, entry))
            await _settle(pilot)
            await pilot.click("#download-btn")
            queue = await _wait_queue_done(pilot)
            self.assertIsInstance(queue, QueueScreen)
            self.assertEqual(queue._finished, True)
            self.assertEqual(provider.calls, ["Movie 2020"])

    async def test_series_skips_seasons_screen(self):
        provider = FakeTorrentProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            entry = provider.search("x")[1]
            pilot.app.push_screen(self._detail(provider, entry))
            await _settle(pilot)
            await pilot.click("#download-btn")
            await _settle(pilot, 8)
            self.assertIsInstance(_active(pilot), QueueScreen)
            await _wait_queue_done(pilot)
            self.assertEqual(provider.calls, ["Show S01"])

    async def test_streaming_button_absent(self):
        provider = FakeTorrentProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            entry = provider.search("x")[0]
            pilot.app.push_screen(self._detail(provider, entry))
            await _settle(pilot)
            self.assertEqual(len(pilot.app.screen.query("#stream-btn")), 0)


if __name__ == "__main__":
    unittest.main()