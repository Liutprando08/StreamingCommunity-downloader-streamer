# Tests for the Z-Library service: Book -> Entries mapping, credential
# resolution order and the download tracker bridge.

from __future__ import annotations

import threading
import unittest
from types import SimpleNamespace
from unittest import mock

import StreamingCommunity.services.zlibrary as service
from StreamingCommunity.services.zlibrary import client as zclient
from StreamingCommunity.services.zlibrary import downloader as dl
from StreamingCommunity.services.zlibrary.mapper import (
    book_to_entry,
    books_to_entries,
    split_book_key,
)
from StreamingCommunity.source.utils.tracker import context_tracker, download_tracker
from StreamingCommunity.zlib_engine import (
    Book,
    DownloadResult,
    NotLoggedIn,
    SearchResult,
)


def _book(**overrides) -> Book:
    data = {
        "id": "123",
        "hash": "abc",
        "name": "Dune",
        "authors": ["Frank Herbert"],
        "year": "1965",
        "language": "english",
        "extension": "EPUB",
        "size": "2 MB",
        "description": "A desert planet.",
        "url": "https://z-lib.gd/book/123/abc",
    }
    data.update(overrides)
    return Book(**data)


class TestBookMapping(unittest.TestCase):
    def test_maps_every_rendered_field(self):
        entry = book_to_entry(_book())

        self.assertIsNotNone(entry)
        self.assertEqual(entry.id, "123:abc")
        self.assertEqual(entry.name, "Dune")
        self.assertEqual(entry.type, "book")
        self.assertEqual(entry.year, "1965")
        self.assertEqual(entry.authors, "Frank Herbert")
        self.assertEqual(entry.provider_language, "english")
        self.assertEqual(entry.extension, "EPUB")
        self.assertEqual(entry.size, "2 MB")
        self.assertEqual(entry.desc, "A desert planet.")
        self.assertEqual(entry.url, "https://z-lib.gd/book/123/abc")

    def test_joins_multiple_authors(self):
        entry = book_to_entry(_book(authors=["Frank Herbert", "Brian Herbert"]))
        self.assertEqual(entry.authors, "Frank Herbert, Brian Herbert")

    def test_skips_books_without_id_or_hash(self):
        self.assertIsNone(book_to_entry(_book(hash="")))
        self.assertIsNone(book_to_entry(_book(id="")))

    def test_books_to_entries_filters_invalid(self):
        entries = books_to_entries([_book(), _book(id="", hash=""), _book(id="9", hash="z")])
        self.assertEqual([entry.id for entry in entries], ["123:abc", "9:z"])

    def test_split_book_key_round_trip(self):
        self.assertEqual(split_book_key("123:abc"), ("123", "abc"))
        self.assertEqual(split_book_key(""), ("", ""))


class _FakeClient:
    def __init__(self, domain="https://z-lib.gd"):
        self.domain = domain
        self._cookies: dict[str, str] = {}
        self.logged_in = False
        self.logged_out = False
        self.login_calls: list[tuple[str, str]] = []

    @property
    def is_logged_in(self) -> bool:
        return self.logged_in

    def set_cookies(self, cookies):
        self._cookies = dict(cookies)
        self.logged_in = True

    def cookies(self):
        return dict(self._cookies)

    def login(self, email, password):
        self.logged_in = True
        self.login_calls.append((email, password))


class TestCredentialResolution(unittest.TestCase):
    def setUp(self):
        zclient.reset_client()
        self.addCleanup(zclient.reset_client)

    def _run(self, *, email="", password="", user_id="", user_key="", session=None):
        values = {
            "email": email,
            "password": password,
            "remix_userid": user_id,
            "remix_userkey": user_key,
        }
        fake = _FakeClient()
        patchers = [
            mock.patch.object(zclient, "Client", return_value=fake),
            mock.patch.object(zclient, "configured_domain", return_value=""),
            mock.patch.object(zclient, "configured_proxy", return_value=""),
            mock.patch.object(zclient, "configured_retries", return_value=3),
            mock.patch.object(
                zclient,
                "_login_value",
                side_effect=lambda key: values.get(key, ""),
            ),
            mock.patch.object(
                zclient,
                "load_session",
                return_value=session,
            )
            if session is not None
            else mock.patch.object(
                zclient, "load_session", side_effect=FileNotFoundError
            ),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        save_patcher = mock.patch.object(zclient, "save_session")
        self.save_mock = save_patcher.start()
        self.addCleanup(save_patcher.stop)
        return fake, zclient.get_client()

    def test_remix_cookies_win_over_everything(self):
        fake, client = self._run(
            email="a@b.c", password="pw", user_id="uid", user_key="ukey"
        )
        self.assertIs(client, fake)
        self.assertEqual(
            fake.cookies(),
            {"remix_userid": "uid", "remix_userkey": "ukey"},
        )
        self.assertEqual(fake.login_calls, [])

    def test_engine_session_is_reused(self):
        session = SimpleNamespace(
            cookies={"remix_userid": "sid", "remix_userkey": "skey"},
            domain="https://z-lib.gd",
        )
        fake, client = self._run(email="a@b.c", password="pw", session=session)
        self.assertIs(client, fake)
        self.assertEqual(
            fake.cookies(),
            {"remix_userid": "sid", "remix_userkey": "skey"},
        )
        self.assertEqual(fake.login_calls, [])

    def test_password_login_persists_the_session(self):
        fake, client = self._run(email="a@b.c", password="pw")
        self.assertIs(client, fake)
        self.assertEqual(fake.login_calls, [("a@b.c", "pw")])
        self.save_mock.assert_called_once()
        saved = self.save_mock.call_args.args[0]
        self.assertEqual(saved.domain, "https://z-lib.gd")

    def test_missing_credentials_raise_actionable_error(self):
        with self.assertRaises(NotLoggedIn) as ctx:
            self._run()
        self.assertIn("Conf/login.json", str(ctx.exception))

    def test_client_is_cached(self):
        fake, first = self._run(email="a@b.c", password="pw")
        with mock.patch.object(zclient, "_login_value", return_value=""):
            second = zclient.get_client()
        self.assertIs(first, second)


class TestTitleSearch(unittest.TestCase):
    def setUp(self):
        service.entries_manager.clear()
        service.table_show_manager.clear()
        self.addCleanup(service.entries_manager.clear)

    def test_maps_search_results(self):
        result = SearchResult(
            books=[_book(), _book(id="", hash="broken")],
            page=1,
            total_pages=1,
        )
        fake = mock.Mock()
        fake.search.return_value = result

        with mock.patch.object(zclient, "get_client", return_value=fake), mock.patch.object(
            zclient, "configured_search_count", return_value=10
        ), mock.patch.object(zclient, "search_options", return_value=None):
            total = service.title_search("dune")

        self.assertEqual(total, 1)
        self.assertEqual(fake.search.call_args.kwargs["count"], 10)
        self.assertEqual(
            [entry.id for entry in service.entries_manager.media_list], ["123:abc"]
        )

    def test_empty_query_skips_the_network(self):
        with mock.patch.object(zclient, "get_client") as get_client:
            self.assertEqual(service.title_search("   "), 0)
        get_client.assert_not_called()

    def test_missing_login_reports_and_returns_zero(self):
        with mock.patch.object(
            zclient, "get_client", side_effect=NotLoggedIn("no login")
        ), mock.patch.object(service, "console") as console:
            self.assertEqual(service.title_search("dune"), 0)
        console.print.assert_called()


class TestDownloader(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, context_tracker, "download_id", None)
        context_tracker.download_id = None

    def _patches(self, fake_client):
        return [
            mock.patch.object(dl.zclient, "get_client", return_value=fake_client),
            mock.patch.object(
                dl, "site_constants", SimpleNamespace(BOOK_FOLDER="/tmp/books")
            ),
            mock.patch.object(dl.os_manager, "create_path", return_value=True),
            mock.patch.object(dl, "console"),
            mock.patch.object(dl.download_tracker, "complete_download"),
        ]

    def test_builds_eapi_url_and_returns_path(self):
        entry = book_to_entry(_book())

        class _Client:
            domain = "https://z-lib.gd"

            def __init__(self):
                self.calls = []

            def download(self, url, folder, progress=None, cancel_event=None):
                self.calls.append((url, folder))
                return DownloadResult(file_path="/tmp/books/Dune.epub", size=42)

        fake = _Client()
        patchers = self._patches(fake)
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        path = dl.download_book(entry)

        self.assertEqual(path, "/tmp/books/Dune.epub")
        self.assertEqual(
            fake.calls,
            [
                (
                    "https://z-lib.gd/eapi/book/123/abc/file",
                    "/tmp/books/Frank Herbert",
                )
            ],
        )

    def test_cancel_event_comes_from_the_tracker(self):
        entry = book_to_entry(_book())
        event = threading.Event()
        download_tracker.stop_events["dl-42"] = event
        self.addCleanup(download_tracker.stop_events.pop, "dl-42", None)
        context_tracker.download_id = "dl-42"

        captured = {}

        class _Client:
            domain = "https://z-lib.gd"

            def download(self, url, folder, progress=None, cancel_event=None):
                captured["cancel_event"] = cancel_event
                return DownloadResult(file_path="/tmp/x.epub", size=1)

        patchers = self._patches(_Client())
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        dl.download_book(entry)
        self.assertIs(captured["cancel_event"], event)

    def test_progress_is_bridged_to_the_tracker(self):
        entry = book_to_entry(_book())
        context_tracker.download_id = "dl-77"

        reporter = dl.BookDownloadReporter(entry)
        with mock.patch.object(dl.download_tracker, "update_progress") as update:
            reporter.progress(50, 100)
        update.assert_called_once()
        args = update.call_args.args
        self.assertEqual(args[0], "dl-77")
        self.assertEqual(args[1], dl.TASK_KEY)
        self.assertAlmostEqual(args[2], 50.0)

    def test_engine_error_returns_none_without_raising(self):
        from StreamingCommunity.zlib_engine import DownloadFailed

        entry = book_to_entry(_book())

        class _Client:
            domain = "https://z-lib.gd"

            def download(self, *args, **kwargs):
                raise DownloadFailed("quota exceeded")

        patchers = self._patches(_Client())
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        self.assertIsNone(dl.download_book(entry))

    def test_output_dir_uses_first_author(self):
        entry = book_to_entry(_book(authors=["Frank Herbert", "Brian Herbert"]))
        with mock.patch.object(
            dl, "site_constants", SimpleNamespace(BOOK_FOLDER="/tmp/books")
        ), mock.patch.object(dl.os_manager, "create_path", return_value=True):
            folder = dl.book_output_dir(entry)
        self.assertEqual(folder, "/tmp/books/Frank Herbert")

    def test_unknown_author_folder(self):
        entry = book_to_entry(_book(authors=[]))
        with mock.patch.object(
            dl, "site_constants", SimpleNamespace(BOOK_FOLDER="/tmp/books")
        ), mock.patch.object(dl.os_manager, "create_path", return_value=True):
            folder = dl.book_output_dir(entry)
        self.assertEqual(folder, "/tmp/books/Unknown")


class TestServiceContract(unittest.TestCase):
    def test_site_metadata(self):
        self.assertEqual(service.indice, 26)
        self.assertEqual(service._useFor, "Books")
        self.assertTrue(callable(service.search))
        self.assertTrue(callable(service.title_search))
        self.assertTrue(callable(service.process_search_result))

    def test_process_result_returns_false_without_a_selection(self):
        with mock.patch.object(service, "console"):
            self.assertFalse(service.process_search_result(None))

    def test_process_result_downloads_and_clears(self):
        entry = book_to_entry(_book())
        with mock.patch.object(
            service, "download_book", return_value="/tmp/book.epub"
        ):
            self.assertTrue(service.process_search_result(entry))


if __name__ == "__main__":
    unittest.main()
