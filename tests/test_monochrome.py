import unittest

from StreamingCommunity.services.monochrome import downloader, scrapper


class TestMonochromeParsing(unittest.TestCase):
    def test_track_entry_from_search(self):
        entry = scrapper._track_entry(
            {
                "id": "1",
                "trackId": "1",
                "title": "Song",
                "artistNames": ["A", "B"],
                "artwork": "http://img",
                "duration": 1000,
            }
        )
        self.assertEqual(entry.name, "Song")
        self.assertEqual(entry.type, "Song")
        self.assertEqual(entry.artist, "A, B")
        self.assertEqual(entry.url, "https://tracks.monochrome.st/track/1")

    def test_track_entry_handles_artist_objects(self):
        entry = scrapper._track_entry(
            {
                "trackId": "9",
                "title": "T",
                "artists": [{"name": "X"}, {"name": "Y"}],
                "trackNumber": 2,
            },
            album="Alb",
            album_artist="Z",
        )
        self.assertEqual(entry.artist, "X, Y")
        self.assertEqual(entry.album, "Alb")
        self.assertEqual(entry.track_number, 2)

    def test_track_entry_falls_back_to_album_artist(self):
        entry = scrapper._track_entry(
            {"trackId": "9", "title": "T"}, album="Alb", album_artist="Z"
        )
        self.assertEqual(entry.artist, "Z")

    def test_release_entry(self):
        entry = scrapper._release_entry(
            {
                "releaseId": "5",
                "title": "Album",
                "artistNames": ["A"],
                "releaseDate": "2001-03-12T00:00:00.000Z",
                "artwork": "http://c",
            }
        )
        self.assertEqual(entry.type, "Album")
        self.assertEqual(entry.year, "2001")
        self.assertEqual(entry.rel_id, "5")

    def test_search_songs_hits_tracks_endpoint(self):
        calls = {}

        def fake_get_json(path, params=None):
            calls["path"] = path
            calls["params"] = params
            return {"tracks": [{"trackId": "1", "title": "S", "artistNames": ["A"]}]}

        original = scrapper._get_json
        scrapper._get_json = fake_get_json
        try:
            manager = scrapper.search_songs("query")
        finally:
            scrapper._get_json = original

        self.assertEqual(calls["path"], "/search/tracks")
        self.assertEqual(calls["params"], {"q": "query", "limit": scrapper.PAGE_LIMIT})
        self.assertEqual(len(manager), 1)
        self.assertEqual(manager.media_list[0].name, "S")

    def test_get_tracks_from_release(self):
        def fake(path, params=None):
            return {
                "title": "Alb",
                "artists": [{"name": "A"}],
                "tracks": [{"trackId": "7", "title": "T"}],
            }

        original = scrapper._get_json
        scrapper._get_json = fake
        try:
            album = scrapper._release_entry({"releaseId": "5", "title": "Alb"})
            manager = scrapper.get_tracks(album)
        finally:
            scrapper._get_json = original

        self.assertEqual(len(manager), 1)
        self.assertEqual(manager.media_list[0].album, "Alb")
        self.assertEqual(manager.media_list[0].artist, "A")


class TestMonochromeExtension(unittest.TestCase):
    def test_extension_from_content_type(self):
        self.assertEqual(downloader._extension("audio/mp4", b""), ".m4a")
        self.assertEqual(downloader._extension("audio/flac; charset=x", b""), ".flac")
        self.assertEqual(downloader._extension("audio/mpeg", b""), ".mp3")

    def test_extension_sniff_fallback(self):
        self.assertEqual(downloader._extension(None, b"fLaC\x00\x00"), ".flac")
        self.assertEqual(downloader._extension(None, b"\x00\x00\x00\x1cftypisom"), ".m4a")
        self.assertEqual(downloader._extension("application/octet-stream", b"OggS"), ".ogg")


if __name__ == "__main__":
    unittest.main()
