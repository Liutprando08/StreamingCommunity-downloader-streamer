from __future__ import annotations

import unittest

from StreamingCommunity.zlib_engine import Client
from StreamingCommunity.zlib_engine.model import Book

from .support import json_reply, server


def logged_in(url: str) -> Client:
    client = Client(domain=url)
    client.set_cookies({"remix_userid": "123", "remix_userkey": "k"})
    return client


class FeedTests(unittest.TestCase):
    def test_recommended_and_popular_feeds(self) -> None:
        seen = []

        def app(request):
            seen.append(request.path)
            return json_reply(
                {
                    "success": 1,
                    "books": [{"id": "1", "hash": "h", "title": "Book"}],
                }
            )

        with server(app) as srv:
            client = logged_in(srv.url)
            self.assertEqual(client.recommended_books()[0].name, "Book")
            self.assertEqual(client.most_popular_books()[0].name, "Book")
            self.assertEqual(
                seen,
                ["/eapi/user/book/recommended", "/eapi/book/most-popular"],
            )

    def test_feed_rejects_entries_without_id_or_hash(self) -> None:
        with server(
            lambda request: json_reply({"success": 1, "books": [{"title": "Book"}]})
        ) as srv:
            client = logged_in(srv.url)
            with self.assertRaises(Exception):
                client.recommended_books()


class SavedTests(unittest.TestCase):
    def test_saved_books_pagination_and_fallback_page(self) -> None:
        seen = []

        def app(request):
            seen.append(request)
            return json_reply(
                {
                    "success": 1,
                    "books": [{"id": "1", "hash": "h", "title": "Saved"}],
                    "pagination": {"total_pages": 4},
                }
            )

        with server(app) as srv:
            client = logged_in(srv.url)
            result = client.saved_books(page=3)
            self.assertEqual(result.page, 3)
            self.assertEqual(result.total_pages, 4)
            self.assertEqual(result.books[0].name, "Saved")
            self.assertEqual(seen[-1].query["page"], ["3"])
            self.assertEqual(seen[-1].query["limit"], ["50"])


class ProfileTests(unittest.TestCase):
    def test_profile_prefers_downloads_today_and_limit(self) -> None:
        def app(request):
            return json_reply(
                {
                    "success": 1,
                    "user": {
                        "id": 123,
                        "name": "Reader",
                        "email": "reader@example.com",
                        "kindle_email": "reader@kindle.com",
                        "isPremium": 1,
                        "confirmed": False,
                        "donations_active": None,
                        "donations_expire": "2027-01-01",
                        "personalDomains": ["mirror.example", 5],
                        "downloads_today": 7,
                        "downloads_limit": 10,
                        "dailyDownloadsCount": 99,
                        "dailyDownloadLimit": 100,
                    },
                }
            )

        with server(app) as srv:
            client = logged_in(srv.url)
            profile = client.get_profile()
            self.assertEqual(profile.download_limit.daily_amount, 7)
            self.assertEqual(profile.download_limit.daily_allowed, 10)
            self.assertEqual(profile.download_limit.daily_remaining, 3)
            self.assertTrue(profile.quota_known)
            self.assertIs(profile.premium, True)
            self.assertIs(profile.confirmed, False)
            self.assertIsNone(profile.donations_active)
            self.assertEqual(profile.personal_domains, ["mirror.example"])
            self.assertEqual(profile.email, "reader@example.com")
            self.assertEqual(client.get_limits().daily_allowed, 10)

    def test_profile_falls_back_to_daily_fields_and_unknown_quota(self) -> None:
        def app(request):
            return json_reply(
                {
                    "success": 1,
                    "user": {"dailyDownloadsCount": 2, "dailyDownloadLimit": 5},
                }
            )

        with server(app) as srv:
            profile = logged_in(srv.url).get_profile()
            self.assertEqual(profile.download_limit.daily_amount, 2)
            self.assertEqual(profile.download_limit.daily_allowed, 5)
            self.assertTrue(profile.quota_known)

        with server(lambda request: json_reply({"success": 1, "user": {}})) as srv:
            profile = logged_in(srv.url).get_profile()
            self.assertFalse(profile.quota_known)
            self.assertEqual(profile.download_limit.daily_remaining, 0)

    def test_profile_rejection(self) -> None:
        with server(lambda request: json_reply({"success": 0, "error": "nope"})) as srv:
            with self.assertRaises(Exception):
                logged_in(srv.url).get_profile()


class HistoryTests(unittest.TestCase):
    def test_history_maps_dates_and_book_fields(self) -> None:
        def app(request):
            return json_reply(
                {
                    "success": 1,
                    "books": [
                        {
                            "id": "1",
                            "hash": "h",
                            "title": "Recent",
                            "author": "Author",
                            "date": "2026-01-01",
                            "extension": "EPUB",
                            "filesizeString": "1 MB",
                        },
                        {
                            "id": "2",
                            "hash": "h2",
                            "title": "Older",
                            "downloaded_at": "2025-01-01",
                        },
                    ],
                    "pagination": {"current": 1, "total_pages": 2},
                }
            )

        with server(app) as srv:
            result = logged_in(srv.url).download_history()
            self.assertEqual(result.total_pages, 2)
            self.assertEqual([item.date for item in result.items], ["2026-01-01", "2025-01-01"])
            self.assertEqual(result.items[0].authors, ["Author"])
            self.assertEqual(result.items[0].extension, "EPUB")
            self.assertEqual(result.items[1].download_url, srv.url + "/eapi/book/2/h2/file")

    def test_delete_history_requires_numeric_id(self) -> None:
        seen = []

        def app(request):
            seen.append(request.path)
            return json_reply({"success": 1})

        with server(app) as srv:
            client = logged_in(srv.url)
            client.delete_download_history("42:abc")
            self.assertEqual(seen, ["/eapi/user/book/42/delete"])
            for bad in ("abc", "42x", ""):
                with self.subTest(bad=bad), self.assertRaises(Exception):
                    client.delete_download_history(bad)


class ModelTests(unittest.TestCase):
    def test_book_json_dict_drops_empty_fields(self) -> None:
        book = Book(id="1", url="https://z-lib.gd/b/1", name="Book")
        self.assertEqual(
            book.json_dict(),
            {"id": "1", "url": "https://z-lib.gd/b/1", "name": "Book"},
        )
        self.assertNotIn("authors", book.json_dict())
        self.assertEqual(book.to_dict()["authors"], None)


if __name__ == "__main__":
    unittest.main()
