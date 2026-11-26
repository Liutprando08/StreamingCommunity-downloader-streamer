from __future__ import annotations

import json
import unittest

from StreamingCommunity.zlib_engine import Client, Extension, Language, OrderOption, SearchOptions
from StreamingCommunity.zlib_engine.errors import (
    BotProtectionError,
    EmptyQuery,
    LoginFailed,
    NotLoggedIn,
    SessionExpired,
    Unsupported,
)
from StreamingCommunity.zlib_engine.model import Book

from .support import json_reply, server


def search_app(record):
    def app(request):
        record.append(request)
        if request.path == "/eapi/user/login":
            return json_reply(
                {
                    "success": 1,
                    "user": {
                        "id": 123,
                        "email": "reader@example.com",
                        "remix_user_key": "legacy-key",
                        "remix_userkey": "key123",
                    },
                }
            )
        if request.path == "/eapi/book/search":
            return json_reply(
                {
                    "success": 1,
                    "books": [
                        {
                            "id": 42,
                            "hash": "abc",
                            "title": "Dune",
                            "author": "Frank Herbert",
                            "year": 1965,
                            "language": "english",
                            "extension": "EPUB",
                            "filesizeString": "1.2 MB",
                            "identifier": "0-306-40615-2",
                            "categories": [{"name": "Fiction"}, {"title": "Sci-Fi"}],
                            "href": "/book/42/abc",
                            "interestScore": 4.5,
                            "qualityScore": 5,
                        }
                    ],
                    "pagination": {"current": 2, "total_pages": 7},
                }
            )
        return json_reply({"success": 0, "error": "not found"}, 404)

    return app


class LoginAndSearchTests(unittest.TestCase):
    def test_login_sends_form_and_stores_remix_credentials(self) -> None:
        seen = []
        with server(search_app(seen)) as srv:
            client = Client(domain=srv.url)
            client.login("reader@example.com", "secret")

            self.assertTrue(client.is_logged_in)
            self.assertEqual(
                client.cookies(),
                {"remix_userid": "123", "remix_userkey": "key123"},
            )
            login = seen[0]
            self.assertEqual(login.method, "POST")
            self.assertEqual(login.form()["email"], ["reader@example.com"])
            self.assertEqual(login.form()["password"], ["secret"])
            self.assertEqual(login.header("accept"), "application/json")
            self.assertEqual(login.header("source"), "android")

    def test_search_sends_filters_and_maps_books(self) -> None:
        seen = []
        with server(search_app(seen)) as srv:
            client = Client(domain=srv.url)
            client.set_cookies({"remix_userid": "123", "remix_userkey": "key123"})
            options = SearchOptions(
                exact=True,
                from_year=2001,
                to_year=2020,
                languages=[Language.CHINESE, Language.ENGLISH],
                extensions=[Extension.EPUB],
                order=OrderOption.BEST_MATCH,
            )
            result = client.search("books", page=2, count=80, options=options)

            request = seen[-1]
            form = request.form()
            self.assertEqual(form["message"], ["books"])
            self.assertEqual(form["page"], ["2"])
            self.assertEqual(form["limit"], ["50"])
            self.assertEqual(form["e"], ["1"])
            self.assertEqual(form["yearFrom"], ["2001"])
            self.assertEqual(form["yearTo"], ["2020"])
            self.assertEqual(form["languages[]"], ["chinese", "english"])
            self.assertEqual(form["extensions[]"], ["epub"])
            self.assertEqual(form["order"], ["bestmatch"])
            self.assertEqual(request.header("source"), "android")
            self.assertEqual(request.header("remix-userid"), "123")
            self.assertEqual(request.header("remix-userkey"), "key123")

            self.assertEqual(result.page, 2)
            self.assertEqual(result.total_pages, 7)
            book = result.books[0]
            self.assertEqual(book.id, "42")
            self.assertEqual(book.name, "Dune")
            self.assertEqual(book.authors, ["Frank Herbert"])
            self.assertEqual(book.categories, "Fiction, Sci-Fi")
            self.assertEqual(book.isbn10, "0306406152")
            self.assertEqual(book.isbn13, "9780306406157")
            self.assertEqual(book.download_url, srv.url + "/eapi/book/42/abc/file")
            self.assertEqual(book.url, srv.url + "/book/42/abc")
            self.assertEqual(book.size, "1.2 MB")
            self.assertEqual(book.rating, "4.5")
            self.assertEqual(book.quality, "5")

    def test_search_requires_login_and_query(self) -> None:
        client = Client(domain="http://127.0.0.1:1")
        with self.assertRaises(NotLoggedIn):
            client.search("dune")
        client.set_cookies({"remix_userid": "1", "remix_userkey": "k"})
        with self.assertRaises(EmptyQuery):
            client.search("")

    def test_login_failure_reports_server_message(self) -> None:
        with server(lambda request: json_reply({"success": 0, "error": "wrong password"})) as srv:
            client = Client(domain=srv.url)
            with self.assertRaises(LoginFailed) as caught:
                client.login("reader@example.com", "bad")
            self.assertIn("wrong password", str(caught.exception))

    def test_revoked_session_is_classified(self) -> None:
        with server(
            lambda request: json_reply({"success": 0, "error": "Please login"}, status=400)
        ) as srv:
            client = Client(domain=srv.url)
            client.set_cookies({"remix_userid": "1", "remix_userkey": "k"})
            with self.assertRaises(SessionExpired):
                client.search("dune")

    def test_bot_protection_status_and_html_title(self) -> None:
        with server(lambda request: json_reply({"success": 1}, status=513)) as srv:
            client = Client(domain=srv.url)
            client.set_cookies({"remix_userid": "1", "remix_userkey": "k"})
            with self.assertRaises(BotProtectionError):
                client.search("dune")

        def blocked(request):
            return (
                200,
                {"Content-Type": "text/html; charset=utf-8"},
                "<html><title>Verifying your browser - DiamWall</title></html>",
            )

        with server(blocked) as srv:
            client = Client(domain=srv.url)
            client.set_cookies({"remix_userid": "1", "remix_userkey": "k"})
            with self.assertRaises(BotProtectionError):
                client.search("dune")

    def test_json_body_mentioning_diamwall_is_not_blocked(self) -> None:
        with server(
            lambda request: json_reply(
                {
                    "success": 1,
                    "books": [{"id": "1", "hash": "h", "title": "Defeating DiamWall"}],
                    "pagination": {"current": 1, "total_pages": 1},
                }
            )
        ) as srv:
            client = Client(domain=srv.url)
            client.set_cookies({"remix_userid": "1", "remix_userkey": "k"})
            result = client.search("diamwall")
            self.assertEqual(result.books[0].name, "Defeating DiamWall")

    def test_fetch_book_uses_id_hash_reference(self) -> None:
        seen = []

        def app(request):
            seen.append(request)
            return json_reply(
                {
                    "success": 1,
                    "book": {"id": "", "hash": "", "title": "Book", "dl": "/dl/1"},
                }
            )

        with server(app) as srv:
            client = Client(domain=srv.url)
            client.set_cookies({"remix_userid": "1", "remix_userkey": "k"})
            book = client.fetch_book("42:abc")
            self.assertEqual(seen[-1].path, "/eapi/book/42/abc")
            self.assertEqual(book.id, "42")
            self.assertEqual(book.hash, "abc")
            self.assertEqual(book.download_url, srv.url + "/eapi/book/42/abc/file")

    def test_fetch_book_rejects_bad_reference(self) -> None:
        client = Client(domain="http://127.0.0.1:1")
        client.set_cookies({"remix_userid": "1", "remix_userkey": "k"})
        for ref in ("", "42", "42:", ":abc", "1:2:3"):
            with self.assertRaises(Exception):
                client.fetch_book(ref)

    def test_full_text_search_is_unsupported(self) -> None:
        client = Client(domain="http://127.0.0.1:1")
        client.set_cookies({"remix_userid": "1", "remix_userkey": "k"})
        with self.assertRaises(Unsupported):
            client.full_text_search("dune messiah")

    def test_fetch_book_details_keeps_failed_entries_zero(self) -> None:
        def app(request):
            if request.path.endswith("/ok"):
                return json_reply({"success": 1, "book": {"id": "1", "hash": "ok", "title": "OK"}})
            return json_reply({"success": 0, "error": "missing"}, status=404)

        with server(app) as srv:
            client = Client(domain=srv.url)
            client.set_cookies({"remix_userid": "1", "remix_userkey": "k"})
            with self.assertRaises(Exception):
                client.fetch_book_details(["1:ok", "2:missing"], fail_fast=True)
            books = client.fetch_book_details(["1:ok"])
            self.assertEqual(books["1:ok"], Book(id="1", hash="ok", name="OK", download_url=srv.url + "/eapi/book/1/ok/file"))


if __name__ == "__main__":
    unittest.main()
