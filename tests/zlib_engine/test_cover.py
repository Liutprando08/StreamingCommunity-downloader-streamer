from __future__ import annotations

import os
import struct
import tempfile
import unittest
from unittest import mock

from StreamingCommunity.zlib_engine import Client, Cover, ZlibError
from StreamingCommunity.zlib_engine.cover import decode_cover, fetch_cover

from .support import Reply, server


def png_bytes(width: int = 10, height: int = 20) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height)
    return signature + ihdr + b"\x08\x06\x00\x00\x00"


class CoverTests(unittest.TestCase):
    def test_decode_png_jpeg_and_gif(self) -> None:
        cover = decode_cover(png_bytes(12, 34))
        self.assertEqual((cover.format, cover.width, cover.height), ("png", 12, 34))
        self.assertEqual(cover.content_type, "image/png")

        gif = b"GIF89a" + struct.pack("<HH", 7, 9) + b"\x00" * 10
        cover = decode_cover(gif)
        self.assertEqual((cover.format, cover.width, cover.height), ("gif", 7, 9))

        jpeg = (
            b"\xff\xd8"
            + b"\xff\xe0"
            + struct.pack(">H", 4)
            + b"\x00\x00"
            + b"\xff\xc0"
            + struct.pack(">H", 17)
            + b"\x08"
            + struct.pack(">HH", 30, 40)
            + b"\x03" * 9
        )
        cover = decode_cover(jpeg)
        self.assertEqual((cover.format, cover.width, cover.height), ("jpeg", 40, 30))

    def test_decode_rejects_bad_dimensions_and_formats(self) -> None:
        for payload in (
            png_bytes(0, 10),
            png_bytes(5000, 10),
            png_bytes(3000, 3000),
            b"not-an-image",
            b"",
        ):
            with self.subTest(payload=payload[:10]), self.assertRaises(ZlibError):
                decode_cover(payload)

    def test_fetch_cover_and_cache(self) -> None:
        requests = []

        def app(request):
            requests.append(request)
            return Reply(body=png_bytes(10, 20), headers={"Content-Type": "image/png"})

        with tempfile.TemporaryDirectory() as cache_dir, server(app) as srv:
            client = Client(domain=srv.url)
            client.set_cover_cache_dir(cache_dir)
            # The engine only accepts HTTPS cover URLs; local tests relax that.
            with mock.patch("StreamingCommunity.zlib_engine.cover._validate_cover_url"):
                cover = fetch_cover(client, srv.url + "/cover.png")
                self.assertIsInstance(cover, Cover)
                self.assertEqual((cover.width, cover.height), (10, 20))
                self.assertEqual(len(os.listdir(cache_dir)), 1)

                again = fetch_cover(client, srv.url + "/cover.png")
                self.assertEqual((again.width, again.height), (10, 20))
                self.assertEqual(len(requests), 1)

    def test_fetch_cover_rejects_http_and_oversized_body(self) -> None:
        with server(lambda request: Reply(body=b"x")) as srv:
            client = Client(domain=srv.url)
            with self.assertRaises(ZlibError):
                fetch_cover(client, "http://example.com/cover.png")

        with server(lambda request: Reply(body=png_bytes() + b"x" * ((2 << 20) + 1))) as srv:
            client = Client(domain=srv.url)
            with mock.patch("StreamingCommunity.zlib_engine.cover._validate_cover_url"), self.assertRaises(ZlibError):
                fetch_cover(client, srv.url + "/cover.png")

    def test_fetch_cover_rejects_non_image(self) -> None:
        with server(lambda request: Reply(body=b"<html>nope</html>", headers={"Content-Type": "text/html"})) as srv:
            client = Client(domain=srv.url)
            with mock.patch("StreamingCommunity.zlib_engine.cover._validate_cover_url"), self.assertRaises(ZlibError):
                fetch_cover(client, srv.url + "/cover.png")


if __name__ == "__main__":
    unittest.main()
