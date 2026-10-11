import inspect
import json
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from textual.screen import Screen
from textual.widgets import DataTable, Input, OptionList, Select, Static
from textual.widgets.data_table import RowKey

import StreamingCommunity.cli.tui.providers.torrent
import StreamingCommunity.services.torrent.downloader
from StreamingCommunity.cli.tui.app import OsteApp
from StreamingCommunity.cli.tui.formatting import (
    detail_lines,
    entry_info,
    escape_markup,
    format_time,
    progress_bar,
    status_badge,
)
from StreamingCommunity.cli.tui.parse import parse_ranges
from StreamingCommunity.cli.tui.providers import registry
from StreamingCommunity.cli.tui.providers.animeunity import AnimeunityProvider
from StreamingCommunity.cli.tui.screens.activity import ActivityScreen
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
from StreamingCommunity.cli.tui.widgets import SelectableTable
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
            # providers + "Attività (Download)" precede "Esci"
            ol.highlighted = len(registry.all()) + 1
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


class TestTuiQueueLayout(unittest.IsolatedAsyncioTestCase):
    async def _open_film_queue(self, pilot, provider):
        pilot.app.push_screen(
            DetailScreen(provider, FakeEntry("Film X"), is_series=False)
        )
        await _settle(pilot)
        await pilot.click("#download-btn")
        return await _wait_queue_done(pilot)

    async def test_summary_tracks_completion(self):
        provider = FakeProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            queue = await self._open_film_queue(pilot, provider)
            summary = str(queue.query_one("#queue-summary", Static).content)
            self.assertIn("1/1", summary)
            self.assertIn("completato", summary)
            self.assertIn("100.0%", summary)

    async def test_row_shows_progress_and_badge_after_refresh(self):
        provider = FakeProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            queue = await self._open_film_queue(pilot, provider)
            queue._refresh()
            await _settle(pilot)
            table = queue.query_one("#queue-table", DataTable)
            row = table.get_row(RowKey(0))
            # columns: mar, job, status, avanzamento, vel, dim
            self.assertIn("completato", str(row[2]))
            self.assertIn("100.0%", str(row[3]))


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
        # A series queue dismisses itself on completion, and `click` may already
        # have run the whole queue to completion before we can look, so wait on
        # QueueScreen's completion counter instead of catching the screen.
        before = QueueScreen.completed
        await pilot.click("#select-all")
        await _settle(pilot, 3)
        await pilot.click("#confirm-btn")
        await _wait_for(pilot, lambda: QueueScreen.completed > before)
        await _settle(pilot, 3)

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

    async def test_seasons_split_layout_structure(self):
        provider = FakeProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            screen = await self._to_seasons(pilot, provider)
            for selector in (
                "#seasons-split",
                "#season-preview-container",
                "#season-preview",
            ):
                self.assertEqual(len(screen.query(selector)), 1, selector)
            # Confirm/back live inside the selection card now.
            self.assertEqual(len(screen.query("#seasons-actions #confirm-btn")), 1)
            self.assertEqual(len(screen.query("#seasons-actions #back-btn")), 1)

    async def test_seasons_preview_tracks_highlight_and_selection(self):
        provider = FakeProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            seasons = await self._to_seasons(pilot, provider)
            preview = seasons.query_one("#season-preview", Static)
            self.assertIn("Serie Y", str(preview.content))
            # Moving the cursor refreshes the highlighted season.
            seasons.query_one("#season-table", SelectableTable).move_cursor(row=1)
            await _settle(pilot)
            self.assertIn("S2", str(preview.content))
            # Selection is reflected in the card footer.
            seasons._apply_ranges("2,3")
            await _settle(pilot)
            self.assertIn("2/3", str(preview.content))

    async def test_episodes_split_layout_and_preview(self):
        provider = FakeProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            seasons = await self._to_seasons(pilot, provider)
            seasons._apply_ranges("1")
            await _settle(pilot)
            await pilot.click("#confirm-btn")
            episodes = await self._wait_episodes(pilot)
            for selector in (
                "#episodes-split",
                "#episode-preview-container",
                "#episode-preview",
            ):
                self.assertEqual(len(episodes.query(selector)), 1, selector)
            preview = episodes.query_one("#episode-preview", Static)
            self.assertIn("Serie Y", str(preview.content))
            self.assertIn("S1", str(preview.content))
            episodes.query_one("#episodes-table", SelectableTable).move_cursor(row=1)
            await _settle(pilot)
            self.assertIn("Ep2", str(preview.content))


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
        self.assertEqual(
            [p.name for p in registry.by_flow("episode")],
            [
                "Streamingcommunity",
                "Animeunity",
                "Raiplay",
                "Mediaset Infinity",
                "Guardaserie",
                "Discovery EU",
                "Discovery US",
                "Pluto TV",
                "Realtime",
                "Dmax",
                "Nove",
                "Food Network",
                "Home Garden TV",
                "Crunchyroll",
            ],
        )
        self.assertEqual(
            [p.name for p in registry.by_flow("atomic")],
            ["Torrent", "YouTube", "MostraGuarda", "Ipersphera"],
        )
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


class TestProviderRegistry(unittest.TestCase):
    """The sidebar is rendered from ``registry.all()``, so a silent alias
    collision (which used to drop a whole provider) must never come back."""

    def test_all_providers_registered(self):
        self.assertEqual(
            sorted(p.name for p in registry.all()),
            [
                "Animeunity",
                "Crunchyroll",
                "Discovery EU",
                "Discovery US",
                "Dmax",
                "Food Network",
                "Goldenmp3",
                "Guardaserie",
                "Home Garden TV",
                "Ipersphera",
                "Mediaset Infinity",
                "MostraGuarda",
                "Musicmp3",
                "Nove",
                "Pluto TV",
                "Raiplay",
                "Realtime",
                "Streamingcommunity",
                "Torrent",
                "YouTube",
            ],
        )

    def test_aliases_are_unique(self):
        aliases = [getattr(p, "alias", p.name) for p in registry.all()]
        self.assertEqual(len(aliases), len(set(aliases)), aliases)

    def test_flows_are_known(self):
        for provider in registry.all():
            self.assertIn(provider.flow, {"episode", "music", "atomic"}, provider.name)

    def test_duplicate_alias_rejected(self):
        from StreamingCommunity.cli.tui.providers import ProviderRegistry

        registry_under_test = ProviderRegistry()
        registry_under_test.register(registry.get("musicmp3"))
        with self.assertRaises(ValueError):
            registry_under_test.register(registry.get("musicmp3"))


class TestTvServiceProviders(unittest.TestCase):
    """The Film/Serie TV services added on top of streamingcommunity."""

    # Services that ship a film downloader and can surface film entries.
    WITH_FILMS = ("raiplay", "mediasetinfinity", "crunchyroll")
    # Services with no film path: every result walks the seasons flow.
    SERIES_ONLY = (
        "guardaserie",
        "discoveryeu",
        "discoveryus",
        "plutotv",
        "realtime",
        "dmax",
        "nove",
        "foodnetwork",
        "homegardentv",
    )
    ALL = WITH_FILMS + SERIES_ONLY

    def test_registry_metadata(self):
        expected = {
            "raiplay": ("Raiplay", "Film_Serie"),
            "mediasetinfinity": ("Mediaset Infinity", "Film_Serie"),
            "guardaserie": ("Guardaserie", "Serie"),
            "discoveryeu": ("Discovery EU", "Film_Serie"),
            "discoveryus": ("Discovery US", "Film_Serie"),
            "plutotv": ("Pluto TV", "Serie"),
            "realtime": ("Realtime", "Serie"),
            "dmax": ("Dmax", "Serie"),
            "nove": ("Nove", "Serie"),
            "foodnetwork": ("Food Network", "Serie"),
            "homegardentv": ("Home Garden TV", "Serie"),
            "crunchyroll": ("Crunchyroll", "Anime"),
        }
        for alias, (name, category) in expected.items():
            provider = registry.get(alias)
            self.assertIsNotNone(provider, alias)
            self.assertEqual(provider.name, name, alias)
            self.assertEqual(provider.category, category, alias)
            self.assertEqual(provider.flow, "episode", alias)
            self.assertTrue(provider.supports_seasons, alias)
            self.assertFalse(provider.supports_streaming, alias)

    def test_implements_episode_protocol(self):
        for alias in self.ALL:
            provider = registry.get(alias)
            for attr in (
                "search",
                "result_columns",
                "is_series",
                "new_series_scraper",
                "seasons",
                "episodes",
                "download_film",
                "download_episode",
            ):
                self.assertTrue(callable(getattr(provider, attr, None)), (alias, attr))

    def test_columns_include_name(self):
        for alias in self.ALL:
            values = dict(registry.get(alias).result_columns()).values()
            self.assertIn("name", values, alias)

    def test_is_series_routing(self):
        film = FakeEntry("Film", type_="film")
        movie = FakeEntry("Movie", type_="movie")
        tv = FakeEntry("Show", type_="tv")

        for alias in self.WITH_FILMS:
            provider = registry.get(alias)
            self.assertFalse(provider.is_series(film), alias)
            self.assertFalse(provider.is_series(movie), alias)
            self.assertTrue(provider.is_series(tv), alias)

        for alias in self.SERIES_ONLY:
            provider = registry.get(alias)
            self.assertTrue(provider.is_series(film), alias)
            self.assertTrue(provider.is_series(tv), alias)

    def test_seasons_and_episodes_delegate_to_scraper(self):
        scraper = SimpleNamespace(
            seasons_manager=SimpleNamespace(
                seasons=[SimpleNamespace(number=1, name="S1")]
            ),
            getNumberSeason=lambda: 1,
            getEpisodeSeasons=lambda s: [SimpleNamespace(number=1, name="Ep1")],
        )
        for alias in self.ALL:
            provider = registry.get(alias)
            self.assertEqual(provider.seasons(scraper)[0].number, 1, alias)
            self.assertEqual(provider.episodes(scraper, 1)[0].name, "Ep1", alias)

    def test_stream_not_offered(self):
        provider = registry.get("raiplay")
        self.assertIsNone(provider.stream_film(FakeEntry("X")))
        self.assertIsNone(provider.stream_episode())


class TestFilmServiceProviders(unittest.TestCase):
    """The single-video services (YouTube, MostraGuarda, Ipersphera)."""

    def test_registry_metadata(self):
        expected = {
            "youtube": ("YouTube", "Film_Serie"),
            "mostraguarda": ("MostraGuarda", "Film"),
            "ipersphera": ("Ipersphera", "Film_Serie"),
        }
        for alias, (name, category) in expected.items():
            provider = registry.get(alias)
            self.assertIsNotNone(provider, alias)
            self.assertEqual(provider.name, name, alias)
            self.assertEqual(provider.category, category, alias)
            self.assertEqual(provider.flow, "atomic", alias)
            self.assertFalse(provider.supports_seasons, alias)
            self.assertFalse(provider.supports_streaming, alias)

    def test_implements_atomic_protocol(self):
        for alias in ("youtube", "mostraguarda", "ipersphera"):
            provider = registry.get(alias)
            for attr in ("search", "result_columns", "is_series", "download_film"):
                self.assertTrue(callable(getattr(provider, attr, None)), (alias, attr))

    def test_every_result_is_a_single_download(self):
        for alias in ("youtube", "mostraguarda", "ipersphera"):
            provider = registry.get(alias)
            for media_type in ("film", "movie", "tv", "serie", None):
                entry = FakeEntry("X", type_=media_type)
                self.assertFalse(provider.is_series(entry), (alias, media_type))

    def test_youtube_columns_show_duration_and_channel(self):
        values = dict(registry.get("youtube").result_columns()).values()
        self.assertIn("name", values)
        self.assertIn("size", values)
        self.assertIn("desc", values)


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


class TestFormatting(unittest.TestCase):
    def test_format_time_of_timestamp(self):
        self.assertEqual(format_time(0), "-")
        self.assertRegex(format_time(1_700_000_000), r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

    def test_format_time_passthrough(self):
        self.assertEqual(format_time("n/a"), "n/a")
        self.assertEqual(format_time(None), "-")

    def test_progress_bar_bounds_and_clamping(self):
        self.assertEqual(progress_bar(0), "░" * 10 + "   0.0%")
        self.assertEqual(progress_bar(100), "█" * 10 + " 100.0%")
        self.assertEqual(progress_bar("bogus"), "░" * 10 + "   0.0%")
        self.assertEqual(progress_bar(-5), "░" * 10 + "   0.0%")
        self.assertEqual(progress_bar(250), "█" * 10 + " 100.0%")

    def test_status_badge_categories(self):
        self.assertIn("in corso", status_badge("downloading"))
        self.assertIn("completato", status_badge("completed"))
        self.assertIn("annullato", status_badge("cancelling..."))
        self.assertIn("scaduto", status_badge("timed_out"))
        self.assertIn("errore", status_badge("failed"))

    def test_detail_lines_aligns_and_filters(self):
        lines = detail_lines([("Anno", "2020"), ("ID", "tt1"), ("Vuoto", "")])
        self.assertEqual(len(lines), 2)  # blank value dropped
        # Labels are padded to the widest one (Anno/ID -> width 4).
        self.assertEqual(lines[0], "[dim]Anno[/]  [#cdd6f4]2020[/]")
        self.assertEqual(lines[1], "[dim]ID  [/]  [#cdd6f4]tt1[/]")

    def test_detail_lines_empty(self):
        self.assertEqual(detail_lines([]), [])
        self.assertEqual(detail_lines([("x", None)]), [])

    def test_detail_lines_escapes_markup(self):
        lines = detail_lines([("Trama", "un [testo] strano")])
        self.assertEqual(lines[0], r"[dim]Trama[/]  [#cdd6f4]un \[testo] strano[/]")

    def test_escape_markup(self):
        self.assertEqual(escape_markup("a[b]c"), r"a\[b]c")
        self.assertEqual(escape_markup(None), "None")

    def test_entry_info_collects_all_attributes(self):
        entry = FakeEntry("X", year="2020", score="9.0", slug="x", url="http://x")
        pairs = dict(
            entry_info(entry, columns=(("Nome", "name"), ("Anno", "year")))
        )
        self.assertEqual(pairs["Nome"], "X")
        self.assertEqual(pairs["Anno"], "2020")
        self.assertEqual(pairs["Punteggio"], "9.0")
        self.assertEqual(pairs["Slug"], "x")
        self.assertEqual(pairs["URL"], "http://x")
        self.assertEqual(pairs["Tipo"], "film")

    def test_entry_info_respects_exclude(self):
        entry = FakeEntry("X", score="9.0")
        labels = [label for label, _ in entry_info(entry, exclude={"name"})]
        self.assertNotIn("Nome", labels)
        self.assertIn("Punteggio", labels)




class TestSelectableTable(unittest.IsolatedAsyncioTestCase):
    async def _open(self, pilot, columns=("A", "B")):
        class _Host(Screen):
            def compose(inner):
                yield SelectableTable(columns, id="t")

        pilot.app.push_screen(_Host())
        await _settle(pilot)
        return _active(pilot).query_one("#t", SelectableTable)

    async def test_set_rows_and_toggle_marker(self):
        async with OsteApp().run_test(size=(80, 24)) as pilot:
            table = await self._open(pilot)
            table.set_rows([("a1", "b1"), ("a2", "b2")])
            await pilot.pause()
            self.assertEqual(table.count, 2)
            self.assertEqual(table.get_row("0")[0], " ")
            table.toggle(1)
            await pilot.pause()
            self.assertEqual(table.get_row("1")[0], "✓")
            self.assertEqual(table.get_row("0")[0], " ")
            self.assertEqual(table.selected, {1})
            table.toggle(1)
            await pilot.pause()
            self.assertEqual(table.selected, set())

    async def test_select_all_none_and_invert(self):
        async with OsteApp().run_test(size=(80, 24)) as pilot:
            table = await self._open(pilot)
            table.set_rows([(f"a{i}", f"b{i}") for i in range(1, 6)])
            await pilot.pause()
            table.select_all()
            self.assertEqual(table.selected, {0, 1, 2, 3, 4})
            table.invert()
            self.assertEqual(table.selected, set())
            table.set_selected({0})
            table.invert()
            self.assertEqual(table.selected, {1, 2, 3, 4})
            table.select_none()
            self.assertEqual(table.selected, set())
            for index in range(5):
                self.assertEqual(table.get_row(str(index))[0], " ")

    async def test_apply_range_is_one_based(self):
        async with OsteApp().run_test(size=(80, 24)) as pilot:
            table = await self._open(pilot)
            table.set_rows([(f"a{i}", f"b{i}") for i in range(1, 6)])
            await pilot.pause()
            table.apply_range("1,3-4")
            self.assertEqual(table.selected, {0, 2, 3})
            table.apply_range("*")
            self.assertEqual(table.selected, {0, 1, 2, 3, 4})

    async def test_set_rows_resets_selection(self):
        async with OsteApp().run_test(size=(80, 24)) as pilot:
            table = await self._open(pilot)
            table.set_rows([(f"a{i}", f"b{i}") for i in range(1, 4)])
            await pilot.pause()
            table.select_all()
            table.set_rows([(f"c{i}", f"d{i}") for i in range(1, 4)])
            await pilot.pause()
            self.assertEqual(table.selected, set())
            self.assertEqual(table.count, 3)


class TestTuiActivity(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._path_patch = mock.patch.object(
            download_tracker,
            "_history_path",
            return_value=os.path.join(self._tmp, "history.json"),
        )
        self._path_patch.start()
        self._saved = (
            dict(download_tracker.downloads),
            list(download_tracker.history),
            dict(download_tracker.stop_events),
            dict(download_tracker.active_processes),
        )

    def tearDown(self):
        download_tracker.downloads.clear()
        download_tracker.downloads.update(self._saved[0])
        download_tracker.history.clear()
        download_tracker.history.extend(self._saved[1])
        download_tracker.stop_events.clear()
        download_tracker.stop_events.update(self._saved[2])
        download_tracker.active_processes.clear()
        download_tracker.active_processes.update(self._saved[3])
        self._path_patch.stop()

    async def _open(self, pilot):
        pilot.app.push_screen(ActivityScreen())
        await _settle(pilot)
        return _active(pilot)

    async def test_home_has_activity_entry(self):
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            ol = _active(pilot).query_one("#menu-list", OptionList)
            prompts = [
                str(ol.get_option_at_index(i).prompt) for i in range(ol.option_count)
            ]
            self.assertTrue(any("Attività" in p for p in prompts))

    async def test_home_opens_activity(self):
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            ol = _active(pilot).query_one("#menu-list", OptionList)
            ol.focus()
            await _settle(pilot)
            ol.highlighted = len(registry.all())
            await _settle(pilot)
            await pilot.press("enter")
            await _settle(pilot)
            self.assertIsInstance(_active(pilot), ActivityScreen)
            await pilot.click("#back-btn")
            await _settle(pilot)
            self.assertIsInstance(_active(pilot), HomeScreen)

    async def test_lists_active_and_history(self):
        download_tracker.downloads.clear()
        download_tracker.history.clear()
        download_tracker.start_download(
            "active-1", "Active Movie", "Streamingcommunity", "Film"
        )
        download_tracker.update_progress(
            "active-1", "video", 42.0, "2MB/s", "10MB/20MB"
        )
        download_tracker.start_download(
            "done-1", "Done Movie", "Streamingcommunity", "Film"
        )
        download_tracker.complete_download("done-1", success=True, path="/x.mp4")

        async with OsteApp().run_test(size=(140, 40)) as pilot:
            screen = await self._open(pilot)
            active = screen.query_one("#active-table", DataTable)
            history = screen.query_one("#history-table", DataTable)
            self.assertEqual(active.row_count, 1)
            self.assertEqual(history.row_count, 1)
            self.assertIn("Active Movie", str(active.get_row("active-1")[1]))
            self.assertIn("Done Movie", str(history.get_row("0")[1]))

    async def test_history_with_duplicate_or_missing_ids_does_not_crash(self):
        download_tracker.downloads.clear()
        download_tracker.history.clear()
        download_tracker.history.extend(
            [
                {"title": "No id A", "status": "completed", "end_time": 1.0},
                {"title": "No id B", "status": "failed", "end_time": 2.0},
                {"id": "dup", "title": "Dup A", "status": "completed", "end_time": 3.0},
                {"id": "dup", "title": "Dup B", "status": "completed", "end_time": 4.0},
            ]
        )

        async with OsteApp().run_test(size=(140, 40)) as pilot:
            screen = await self._open(pilot)
            self.assertEqual(
                screen.query_one("#history-table", DataTable).row_count, 4
            )

    async def test_cancel_requests_stop(self):
        download_tracker.downloads.clear()
        download_tracker.history.clear()
        download_tracker.start_download(
            "cancel-1", "Cancel Me", "Streamingcommunity", "Film"
        )

        async with OsteApp().run_test(size=(140, 40)) as pilot:
            screen = await self._open(pilot)
            table = screen.query_one("#active-table", DataTable)
            table.focus()
            table.move_cursor(row=0)
            await _settle(pilot)
            await pilot.click("#cancel-btn")
            await _settle(pilot)
            self.assertTrue(download_tracker.is_stopped("cancel-1"))

    async def test_clear_history(self):
        download_tracker.downloads.clear()
        download_tracker.history.clear()
        download_tracker.history.append(
            {
                "id": "h1",
                "title": "Old",
                "status": "completed",
                "type": "Film",
                "size": "1B",
                "path": "/old.mp4",
                "end_time": 1_700_000_000,
            }
        )

        async with OsteApp().run_test(size=(140, 40)) as pilot:
            screen = await self._open(pilot)
            self.assertEqual(
                screen.query_one("#history-table", DataTable).row_count, 1
            )
            await pilot.click("#clear-btn")
            await _settle(pilot)
            self.assertEqual(len(download_tracker.history), 0)
            self.assertEqual(
                screen.query_one("#history-table", DataTable).row_count, 0
            )


class TestTuiSearchLayout(unittest.IsolatedAsyncioTestCase):
    async def _open(self, pilot, provider):
        pilot.app.push_screen(SearchScreen(provider))
        await _settle(pilot)
        return _active(pilot)

    async def _search(self, pilot, screen, query="fake", via_button=False):
        field = screen.query_one("#search-input", Input)
        field.value = query
        field.focus()
        await _settle(pilot)
        if via_button:
            await pilot.click("#search-btn")
        else:
            await pilot.press("enter")

        async def loaded():
            active = _active(pilot)
            if isinstance(active, SearchScreen) and active._entries:
                return active
            return None

        return await _wait_for(pilot, loaded)

    async def test_split_layout_structure(self):
        provider = FakeProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            screen = await self._open(pilot, provider)
            for selector in (
                "#search-split",
                "#table-box",
                "#preview-container",
                "#search-preview",
                "#preview-open-btn",
            ):
                self.assertEqual(len(screen.query(selector)), 1, selector)

    async def test_results_populate_preview(self):
        provider = FakeProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            screen = await self._open(pilot, provider)
            screen = await self._search(pilot, screen)
            preview = screen.query_one("#search-preview", Static)
            self.assertIn("Fake Film", str(preview.content))

    async def test_highlight_updates_preview(self):
        provider = FakeProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            screen = await self._open(pilot, provider)
            screen = await self._search(pilot, screen)
            screen.query_one("#results", DataTable).move_cursor(row=1)
            await _settle(pilot)
            preview = screen.query_one("#search-preview", Static)
            self.assertIn("Fake Serie", str(preview.content))
            self.assertIn("Serie", str(preview.content))

    async def test_search_button_runs_query(self):
        provider = FakeProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            screen = await self._open(pilot, provider)
            screen = await self._search(pilot, screen, via_button=True)
            self.assertEqual(len(screen._entries), 2)

    async def test_preview_button_opens_detail(self):
        provider = FakeProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            screen = await self._open(pilot, provider)
            screen = await self._search(pilot, screen)
            screen.query_one("#results", DataTable).move_cursor(row=0)
            await _settle(pilot)
            await pilot.click("#preview-open-btn")
            await _settle(pilot)
            self.assertIsInstance(_active(pilot), DetailScreen)


class TestTuiDetailLayout(unittest.IsolatedAsyncioTestCase):
    def _detail(self, provider, entry):
        return DetailScreen(provider, entry, is_series=provider.is_series(entry))

    async def test_split_layout_structure(self):
        provider = FakeProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            pilot.app.push_screen(self._detail(provider, FakeEntry("Film X")))
            await _settle(pilot)
            screen = _active(pilot)
            for selector in (
                "#detail-split",
                "#info-box",
                "#actions-box",
                "#entry-title",
                "#entry-badges",
                "#entry-details",
            ):
                self.assertEqual(len(screen.query(selector)), 1, selector)

    async def test_shows_title_and_provider_metadata(self):
        provider = FakeProvider()
        entry = FakeEntry("Film X", year="1999", imdb_id="tt999")
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            pilot.app.push_screen(self._detail(provider, entry))
            await _settle(pilot)
            screen = _active(pilot)
            self.assertIn(
                "Film X", str(screen.query_one("#entry-title", Static).content)
            )
            badges = str(screen.query_one("#entry-badges", Static).content)
            self.assertIn("Film", badges)
            self.assertIn("Streamingcommunity", badges)
            details = str(screen.query_one("#entry-details", Static).content)
            self.assertIn("1999", details)
            self.assertIn("tt999", details)

    async def test_series_badge(self):
        provider = FakeProvider()
        entry = FakeEntry("Serie Y", type_="tv")
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            pilot.app.push_screen(self._detail(provider, entry))
            await _settle(pilot)
            screen = _active(pilot)
            self.assertIn(
                "Serie", str(screen.query_one("#entry-badges", Static).content)
            )

    async def test_description_shown_when_present(self):
        provider = FakeProvider()
        entry = FakeEntry("Film X", desc="Una trama epica.")
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            pilot.app.push_screen(self._detail(provider, entry))
            await _settle(pilot)
            screen = _active(pilot)
            self.assertIn(
                "Una trama epica.",
                str(screen.query_one("#entry-desc", Static).content),
            )

    async def test_description_hidden_when_absent(self):
        provider = FakeProvider()
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            pilot.app.push_screen(self._detail(provider, FakeEntry("Film X")))
            await _settle(pilot)
            screen = _active(pilot)
            self.assertFalse(screen.query_one("#entry-desc", Static).display)

    async def test_shows_all_entry_fields(self):
        provider = FakeProvider()
        entry = FakeEntry(
            "Film X",
            year="1999",
            imdb_id="tt999",
            score="9.1",
            slug="film-x",
            url="http://example/film-x",
        )
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            pilot.app.push_screen(self._detail(provider, entry))
            await _settle(pilot)
            screen = _active(pilot)
            details = str(screen.query_one("#entry-details", Static).content)
            for token in (
                "1999",
                "tt999",
                "9.1",
                "film-x",
                "http://example/film-x",
                "Punteggio",
                "Slug",
                "URL",
            ):
                self.assertIn(token, details, token)

    async def test_description_markup_is_escaped(self):
        provider = FakeProvider()
        entry = FakeEntry("Film X", desc="Un [capolavoro] assoluto.")
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            pilot.app.push_screen(self._detail(provider, entry))
            await _settle(pilot)
            screen = _active(pilot)
            content = str(screen.query_one("#entry-desc", Static).content)
            self.assertIn(r"\[capolavoro]", content)
            self.assertIn("assoluto.", content)

    async def test_full_description_replaces_truncated(self):
        class DescribedProvider(FakeProvider):
            def entry_description(self, entry):
                return "Trama completa e dettagliata. " * 20

        provider = DescribedProvider()
        entry = FakeEntry("Film X", desc="trama tronca")
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            pilot.app.push_screen(self._detail(provider, entry))
            await _settle(pilot)

            async def updated():
                widget = pilot.app.screen.query_one("#entry-desc", Static)
                return "Trama completa e dettagliata." in str(widget.content)

            await _wait_for(pilot, updated)
            screen = _active(pilot)
            self.assertEqual(screen.query_one("#entry-desc", Static).display, True)

    async def test_keeps_api_description_without_enricher(self):
        provider = FakeProvider()  # no entry_description capability
        entry = FakeEntry("Film X", desc="trama dell'api")
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            pilot.app.push_screen(self._detail(provider, entry))
            await _settle(pilot)
            content = str(
                _active(pilot).query_one("#entry-desc", Static).content
            )
            self.assertIn("trama dell'api", content)



    async def test_torrent_metadata_columns(self):
        provider = FakeTorrentProvider()
        entry = provider.search("x")[0]
        async with OsteApp().run_test(size=(140, 40)) as pilot:
            pilot.app.push_screen(self._detail(provider, entry))
            await _settle(pilot)
            screen = _active(pilot)
            details = str(screen.query_one("#entry-details", Static).content)
            self.assertIn("Seed", details)
            # Torrent provider does not stream, so its button is absent.
            self.assertEqual(len(screen.query("#stream-btn")), 0)


class TestFullDescription(unittest.TestCase):
    """The site truncates the plot; the detail page recovers the full one."""

    @staticmethod
    def _page(slug, items, paragraph=None):
        scripts = []
        for slug_value, plot in items:
            inner = json.dumps(
                {"slug": slug_value, "plot": plot}, separators=(",", ":")
            )
            scripts.append(
                "<script>self.__next_f.push([1," + json.dumps(inner) + "])</script>"
            )
        page = "<html>" + "".join(scripts)
        if paragraph is not None:
            page += f'<p class="tc-plot">{paragraph}</p>'
        return page + "</html>"

    def test_extracts_full_plot_by_slug(self):
        from StreamingCommunity.services.streamingcommunity import _extract_plot

        full = "Trama completa e dettagliata. " * 30
        page = self._page(
            "matrix",
            [("other-movie", "Trama di un altro film."), ("matrix", full)],
        )
        self.assertEqual(_extract_plot(page, "matrix"), full.strip())

    def test_ignores_null_plot_and_uses_paragraph(self):
        from StreamingCommunity.services.streamingcommunity import _extract_plot

        page = self._page("matrix", [("matrix", None)], paragraph="Trama breve…")
        self.assertEqual(_extract_plot(page, "matrix"), "Trama breve")

    def test_returns_none_without_plot(self):
        from StreamingCommunity.services.streamingcommunity import _extract_plot

        self.assertIsNone(_extract_plot("<html></html>", "matrix"))

    def test_plot_from_payload_keeps_inner_quotes(self):
        from StreamingCommunity.services.streamingcommunity import (
            _plot_from_payload,
        )

        payload = json.dumps(
            {"slug": "x", "plot": 'un "capolavoro" assoluto'},
            separators=(",", ":"),
        )
        self.assertEqual(
            _plot_from_payload(payload, "x"), 'un "capolavoro" assoluto'
        )


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