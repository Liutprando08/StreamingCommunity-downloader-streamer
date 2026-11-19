from __future__ import annotations

import os
import tempfile
import unittest

from StreamingCommunity.zlib_engine import Client, DownloadFailed, sanitize_filename
import StreamingCommunity.zlib_engine.download as download_module
from StreamingCommunity.zlib_engine.download import clean_filename

from .support import Reply, json_reply, server

BOOK = b"epub-bytes" * 100


class DownloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_base = download_module.download_retry_base
        download_module.download_retry_base = 0.0
        self.addCleanup(setattr, download_module, "download_retry_base", self._old_base)

    def _app(self, requests, file_status=200):
        def app(request):
            requests.append(request)
            base = "http://" + request.header("host")
            if request.path == "/eapi/book/1/h/file":
                return json_reply(
                    {"success": 1, "file": {"downloadLink": base + "/files/book.epub"}}
                )
            if request.path == "/files/book.epub":
                return Reply(
                    status=file_status,
                    body=BOOK,
                    headers={
                        "Content-Type": "application/epub+zip",
                        "Content-Disposition": 'attachment; filename="book.epub"',
                    },
                )
            return Reply(status=404, body=b"missing")

        return app

    def test_download_resolves_eapi_link_and_writes_atomically(self) -> None:
        requests = []
        with tempfile.TemporaryDirectory() as directory, server(self._app(requests)) as srv:
            client = Client(domain=srv.url)
            client.set_cookies({"remix_userid": "1", "remix_userkey": "k"})
            result = client.download(srv.url + "/eapi/book/1/h/file", directory)

            self.assertEqual(result.size, len(BOOK))
            self.assertEqual(result.file_path, os.path.join(directory, "book.epub"))
            with open(result.file_path, "rb") as handle:
                self.assertEqual(handle.read(), BOOK)
            self.assertEqual([name for name in os.listdir(directory) if name.endswith(".part")], [])
            eapi = next(request for request in requests if request.path.startswith("/eapi/"))
            self.assertEqual(eapi.header("remix-userkey"), "k")

    def test_download_does_not_send_account_cookies_to_another_origin(self) -> None:
        requests = []

        def app(request):
            requests.append(request)
            return Reply(body=BOOK, headers={"Content-Disposition": 'filename="book.epub"'})

        with tempfile.TemporaryDirectory() as directory:
            with server(lambda request: json_reply({})) as mirror:
                client = Client(domain=mirror.url)
                client.set_cookies({"remix_userid": "1", "remix_userkey": "k"})
                with server(app, bind="0.0.0.0", host="127.0.0.2") as cdn:
                    result = client.download(cdn.url + "/book.epub", directory)
                    self.assertEqual(result.size, len(BOOK))
                    self.assertEqual(requests[0].header("cookie"), "")
                    self.assertEqual(requests[0].header("remix-userkey"), "")

    def test_failed_download_keeps_existing_file(self) -> None:
        requests = []
        with tempfile.TemporaryDirectory() as directory, server(
            self._app(requests, file_status=404)
        ) as srv:
            dest = os.path.join(directory, "book.epub")
            with open(dest, "wb") as handle:
                handle.write(b"old")
            client = Client(domain=srv.url)
            client.set_cookies({"remix_userid": "1", "remix_userkey": "k"})
            with self.assertRaises(DownloadFailed):
                client.download(srv.url + "/files/book.epub", directory)
            with open(dest, "rb") as handle:
                self.assertEqual(handle.read(), b"old")

    def test_download_retries_transient_gateway_errors(self) -> None:
        state = {"count": 0}

        def app(request):
            state["count"] += 1
            if state["count"] <= 2:
                return Reply(status=503, body=b"busy")
            return Reply(body=b"done", headers={"Content-Disposition": 'filename="book.epub"'})

        with tempfile.TemporaryDirectory() as directory, server(app) as srv:
            client = Client(domain=srv.url, download_retries=3)
            client.set_cookies({"remix_userid": "1", "remix_userkey": "k"})
            result = client.download(srv.url + "/book.epub", directory)
            self.assertEqual(result.size, 4)
            self.assertEqual(state["count"], 3)

    def test_download_gives_up_after_retries(self) -> None:
        state = {"count": 0}

        def app(request):
            state["count"] += 1
            return Reply(status=502, body=b"bad gateway")

        with tempfile.TemporaryDirectory() as directory, server(app) as srv:
            client = Client(domain=srv.url, download_retries=2)
            client.set_cookies({"remix_userid": "1", "remix_userkey": "k"})
            with self.assertRaises(DownloadFailed):
                client.download(srv.url + "/book.epub", directory)
            self.assertEqual(state["count"], 3)

    def test_download_requires_login(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = Client(domain="http://127.0.0.1:1")
            with self.assertRaises(Exception):
                client.download("http://127.0.0.1:1/book.epub", directory)

    def test_sanitize_filename(self) -> None:
        cases = {
            "book.epub": "book.epub",
            "../../../../etc/passwd": "passwd",
            "..\\..\\..\\Windows\\System32\\evil.dll": "evil.dll",
            "/etc/cron.d/job": "job",
            "a/b/c/book.pdf": "book.pdf",
            "..": "download",
            "": "download",
            ".": "download",
            "Dune\x1b]52;c;ZXZpbA==\x07\x1b[2J.epub": "Dune]52;c;ZXZpbA==[2J.epub",
            "\x1b\x07": "download",
            "Dune: Messiah.epub": "Dune: Messiah.epub",
            "book\u202Ebupe.exe": "bookbupe.exe",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(sanitize_filename(name, "linux"), expected)

    def test_sanitize_filename_for_windows(self) -> None:
        cases = {
            "Dune: Messiah.epub": "Dune_ Messiah.epub",
            'a<b>c"d|e?f*g.pdf': "a_b_c_d_e_f_g.pdf",
            "CON.epub": "_CON.epub",
            "lpt1": "_lpt1",
            "Console.epub": "Console.epub",
            "trailing dot.": "trailing dot",
            "C:\\books\\Dune.epub": "Dune.epub",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(sanitize_filename(name, "windows"), expected)

    def test_clean_filename_drops_zlibrary_domain_group(self) -> None:
        self.assertEqual(
            clean_filename("Dune (z-library.sk, z-lib.fm).epub"),
            "Dune.epub",
        )
        self.assertEqual(clean_filename("Dune (2005).epub"), "Dune (2005).epub")

    def test_download_rejects_path_traversal_in_header(self) -> None:
        def app(request):
            return Reply(body=b"x", headers={"Content-Disposition": 'filename="../../evil.sh"'})

        with tempfile.TemporaryDirectory() as directory, server(app) as srv:
            client = Client(domain=srv.url)
            client.set_cookies({"remix_userid": "1", "remix_userkey": "k"})
            result = client.download(srv.url + "/book", directory)
            self.assertEqual(os.path.basename(result.file_path), "evil.sh")
            self.assertEqual(os.path.dirname(result.file_path), directory)


if __name__ == "__main__":
    unittest.main()
