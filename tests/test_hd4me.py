from __future__ import annotations

import os
import unittest
from unittest import mock

import StreamingCommunity.services.hd4me as hd4me
from StreamingCommunity.cli.tui.providers import registry
from StreamingCommunity.services._base import Entries, site_constants
from StreamingCommunity.services.hd4me import downloader, scrapper

SAMPLE_INDEX = [
    {
        "pid": 9672,
        "twy": "…altrimenti ci arrabbiamo!",
        "to": "...altrimenti ci arrabbiamo!",
        "pa": "27bKMOKfVtOicxZPP1Nk78WyCFE",
        "tay": [{"t": "BRRip m720p – ITA/ENG 1.3 GB", "pid": 9672}],
        "y": "1974",
        "d": 102,
        "iid": "0069697",
        "rt": 7.3,
    },
    {
        "pid": 21793,
        "twy": "1997: Fuga da New York",
        "to": "Escape from New York",
        "pa": "",
        "tay": [
            {"t": "BDRip m720p – ITA/ENG 1.9 GB", "pid": 21793},
            {"t": "BRRip m720p – ITA/ENG 1.76 GB", "pid": 11828},
        ],
        "y": "1981",
        "d": 99,
        "iid": "0082340",
        "rt": 7.2,
    },
    {
        "pid": 333,
        "twy": "L'ultimo bacio",
        "to": "The Last Kiss",
        "pa": "",
        "tay": [{"t": "DVDRip 576p – ITA 700 MB", "pid": 333}],
        "y": "2001",
        "d": 115,
        "iid": "",
        "rt": "N/A",
    },
]

POST_DETAIL = {
    "id": 9672,
    "online": True,
    "movie": {
        "test": "https://mega.nz/file/DsgwBBYY#gnF5jCU7psNqdrdvDVwtZJyDNY8T_Ppu8ccWcFA6IxQ",
        "plot": "Ben e Kid sono rispettivamente un meccanico e un camionista.",
    },
}


class TestIndexParsing(unittest.TestCase):
    def test_build_entries_expands_each_variant(self):
        entries = scrapper._build_entries(SAMPLE_INDEX[1], "https://hd4me.net")

        self.assertEqual([entry.id for entry in entries], [21793, 11828])
        self.assertEqual(entries[0].name, "1997: Fuga da New York")
        self.assertEqual(entries[0].type, "film")
        self.assertEqual(entries[0].year, "1981")
        self.assertEqual(entries[0].imdb_id, "tt0082340")
        self.assertEqual(entries[0].size, "1.9 GB")
        self.assertEqual(entries[1].size, "1.76 GB")
        self.assertEqual(entries[0].url, "https://hd4me.net/21793")
        self.assertEqual(entries[1].url, "https://hd4me.net/11828")

    def test_poster_prefers_tmdb_hash_and_falls_back_to_imdb(self):
        first = scrapper._build_entries(SAMPLE_INDEX[0], "https://hd4me.net")[0]
        second = scrapper._build_entries(SAMPLE_INDEX[1], "https://hd4me.net")[0]

        self.assertEqual(
            first.image,
            "https://image.tmdb.org/t/p/w342/27bKMOKfVtOicxZPP1Nk78WyCFE.jpg",
        )
        self.assertEqual(
            second.image,
            "https://hd4me.net/wp-content/uploads/poster/s/0082340.webp",
        )

    def test_size_parser_and_rating(self):
        self.assertEqual(
            scrapper._extract_size("WEB-DLRip m720p – ITA/ENG 2.41 GB"), "2.41 GB"
        )
        self.assertEqual(scrapper._extract_size("no size here"), "")
        self.assertEqual(scrapper._rating({"rt": 7}), "7.0")
        self.assertEqual(scrapper._rating({"rt": "N/A"}), "")


class TestSearch(unittest.TestCase):
    def test_matches_title_original_year_imdb_and_release_label(self):
        self.assertEqual(
            [entry.id for entry in scrapper.search_index("escape from new york", SAMPLE_INDEX)],
            [21793, 11828],
        )
        self.assertEqual(
            [entry.id for entry in scrapper.search_index("tt0082340", SAMPLE_INDEX)],
            [21793, 11828],
        )
        self.assertEqual(
            [entry.id for entry in scrapper.search_index("1981", SAMPLE_INDEX)],
            [21793, 11828],
        )
        # Matching happens at the title level, so every variant of the item is
        # returned even when only one release label contains the query.
        self.assertEqual(
            [entry.id for entry in scrapper.search_index("BDRip", SAMPLE_INDEX)],
            [21793, 11828],
        )
        self.assertEqual(
            [entry.id for entry in scrapper.search_index("altrimenti", SAMPLE_INDEX)],
            [9672],
        )

    def test_matching_ignores_accents_and_apostrophe_style(self):
        for query in ("l'ultimo", "l’ultimo", "ultimo"):
            with self.subTest(query=query):
                self.assertEqual(
                    [entry.id for entry in scrapper.search_index(query, SAMPLE_INDEX)],
                    [333],
                )

    def test_empty_and_unmatched_queries(self):
        self.assertEqual(scrapper.search_index("", SAMPLE_INDEX), [])
        self.assertEqual(scrapper.search_index("matrix", SAMPLE_INDEX), [])

    def test_results_are_capped(self):
        with mock.patch.object(scrapper, "MAX_RESULTS", 1):
            entries = scrapper.search_index("fuga", SAMPLE_INDEX)
        self.assertEqual(len(entries), 1)

    def test_search_downloads_index_when_not_provided(self):
        with mock.patch.object(scrapper, "get_index", return_value=SAMPLE_INDEX) as get_index:
            self.assertEqual(len(scrapper.search_index("altrimenti")), 1)
        get_index.assert_called_once_with()


class TestIndexRefresh(unittest.TestCase):
    def test_get_index_downloads_on_every_call(self):
        with (
            mock.patch.object(scrapper, "download_index", return_value=SAMPLE_INDEX) as download,
            mock.patch.object(scrapper, "load_local_index") as local,
        ):
            self.assertEqual(scrapper.get_index(), SAMPLE_INDEX)
            self.assertEqual(scrapper.get_index(), SAMPLE_INDEX)

        self.assertEqual(download.call_count, 2)
        local.assert_not_called()

    def test_get_index_falls_back_to_bundled_copy(self):
        with (
            mock.patch.object(
                scrapper, "download_index", side_effect=RuntimeError("offline")
            ) as download,
            mock.patch.object(scrapper, "load_local_index", return_value=SAMPLE_INDEX) as local,
        ):
            self.assertEqual(scrapper.get_index(), SAMPLE_INDEX)

        download.assert_called_once_with()
        local.assert_called_once_with()

    def test_title_search_refreshes_index_each_time(self):
        with mock.patch.object(hd4me, "get_index", return_value=SAMPLE_INDEX) as get_index:
            self.assertEqual(hd4me.title_search("altrimenti"), 1)
            self.assertEqual(hd4me.title_search("altrimenti"), 1)

        self.assertEqual(get_index.call_count, 2)
        hd4me.entries_manager.clear()


class TestPostDetail(unittest.TestCase):
    def test_get_post_uses_the_post_cache_url(self):
        with mock.patch.object(scrapper, "_get_json", return_value=POST_DETAIL) as get_json:
            self.assertEqual(scrapper.get_post(9672), POST_DETAIL)

        get_json.assert_called_once_with(
            f"{scrapper._cache_url()}/posts/9672.json"
        )

    def test_get_download_url_returns_movie_test(self):
        entry = Entries(id=9672, name="…altrimenti ci arrabbiamo!")
        with mock.patch.object(scrapper, "get_post", return_value=POST_DETAIL):
            self.assertEqual(
                scrapper.get_download_url(entry),
                POST_DETAIL["movie"]["test"],
            )

    def test_get_download_url_rejects_offline_and_missing_links(self):
        entry = Entries(id=1, name="X")
        with mock.patch.object(
            scrapper, "get_post", return_value={"online": False, "movie": {}}
        ):
            with self.assertRaises(ValueError):
                scrapper.get_download_url(entry)

        with mock.patch.object(
            scrapper, "get_post", return_value={"online": True, "movie": {}}
        ):
            with self.assertRaises(ValueError):
                scrapper.get_download_url(entry)

    def test_get_full_description_is_cached(self):
        scrapper._description_cache.clear()
        entry = Entries(id=999001, name="X")
        with mock.patch.object(scrapper, "get_post", return_value=POST_DETAIL) as get_post:
            self.assertEqual(
                scrapper.get_full_description(entry),
                POST_DETAIL["movie"]["plot"],
            )
            self.assertEqual(
                scrapper.get_full_description(entry),
                POST_DETAIL["movie"]["plot"],
            )

        get_post.assert_called_once_with(999001)
        scrapper._description_cache.clear()


class FakeMega:
    calls: list = []

    def __init__(self, choose_files=False):
        FakeMega.calls.append(("init", choose_files))

    def download_url(self, url, dest_path=None):
        FakeMega.calls.append((url, dest_path))
        return "/tmp/output"


class TestDownloader(unittest.TestCase):
    def setUp(self):
        FakeMega.calls = []

    def _run(self, detail):
        entry = Entries(
            id=9672,
            name="…altrimenti ci arrabbiamo!",
            type="film",
            year="1974",
        )
        with (
            mock.patch.object(downloader.scrapper, "get_post", return_value=detail),
            mock.patch.object(downloader, "MEGA_Downloader", FakeMega),
        ):
            return downloader.download_film(entry)

    def test_downloads_mega_file_into_movie_folder(self):
        result = self._run(POST_DETAIL)

        self.assertEqual(result, "/tmp/output")
        self.assertEqual(FakeMega.calls[0], ("init", False))
        url, dest_path = FakeMega.calls[1]
        self.assertEqual(url, POST_DETAIL["movie"]["test"])
        self.assertTrue(dest_path.startswith(site_constants.MOVIE_FOLDER))
        self.assertIn("altrimenti", dest_path.lower())

    def test_downloads_mega_folder_into_series_folder(self):
        detail = {
            "online": True,
            "movie": {"test": "https://mega.nz/folder/abc#def"},
        }

        result = self._run(detail)

        self.assertEqual(result, "/tmp/output")
        _, dest_path = FakeMega.calls[1]
        self.assertEqual(os.path.dirname(dest_path), site_constants.SERIES_FOLDER)

    def test_rejects_offline_posts(self):
        detail = {"online": False, "movie": {"test": "https://mega.nz/file/x#y"}}
        self.assertIsNone(self._run(detail))
        self.assertEqual(FakeMega.calls, [])

    def test_rejects_unsupported_host(self):
        detail = {"online": True, "movie": {"test": "https://example.com/file"}}
        self.assertIsNone(self._run(detail))
        self.assertEqual(FakeMega.calls, [])

    def test_rejects_zerobin_links(self):
        detail = {"online": True, "movie": {"test": "https://i.hd4me.net/?x#y"}}
        self.assertIsNone(self._run(detail))
        self.assertEqual(FakeMega.calls, [])


class FakeEntry:
    def __init__(self, name, type_="film", **extra):
        self.name = name
        self.type = type_
        for key, value in extra.items():
            setattr(self, key, value)


class TestTuiProvider(unittest.TestCase):
    def setUp(self):
        self.provider = registry.get("hd4me")
        hd4me.entries_manager.clear()

    def tearDown(self):
        hd4me.entries_manager.clear()

    def test_registry_metadata_and_columns(self):
        self.assertIsNotNone(self.provider)
        self.assertEqual(self.provider.name, "HD4ME")
        self.assertEqual(self.provider.category, "Film_Serie")
        self.assertEqual(self.provider.flow, "atomic")
        self.assertFalse(self.provider.supports_streaming)
        self.assertFalse(self.provider.supports_seasons)

        values = dict(self.provider.result_columns()).values()
        self.assertIn("name", values)
        self.assertIn("type", values)
        self.assertIn("year", values)
        self.assertIn("size", values)

    def test_every_result_is_a_single_download(self):
        for media_type in ("film", "movie", "tv", "serie", None):
            with self.subTest(media_type=media_type):
                self.assertFalse(self.provider.is_series(FakeEntry("X", type_=media_type)))

    def test_search_downloads_the_index(self):
        with mock.patch.object(hd4me, "get_index", return_value=SAMPLE_INDEX) as get_index:
            results = self.provider.search("altrimenti")

        self.assertEqual([entry.id for entry in results], [9672])
        get_index.assert_called_once_with()

    def test_description_uses_the_post_plot(self):
        with mock.patch.object(
            hd4me, "get_full_description", return_value="A plot."
        ) as description:
            self.assertEqual(
                self.provider.entry_description(FakeEntry("X")),
                "A plot.",
            )
        description.assert_called_once()


if __name__ == "__main__":
    unittest.main()
