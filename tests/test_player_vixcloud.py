from __future__ import annotations

import unittest
from unittest import mock

from httpx2 import HTTPError

from StreamingCommunity.player import vixcloud

EMBED_URL = (
    "https://vixcloud.cc/embed/304645"
    "?token=embedtoken&expires=1799492226&canPlayFHD=1"
)

# AnimeUnity serves the embed URL inside the Inertia ``data-page`` prop of the
# episode page (``/anime/{anime}-{slug}/{video}``).
EMBED_PAGE_HTML = (
    '<html><body><div id="app" data-page="'
    '{&quot;component&quot;:&quot;Anime&quot;,&quot;props&quot;:'
    '{&quot;embedUrl&quot;:&quot;' + EMBED_URL + '&quot;}}"></div></body></html>'
)

EMBED_HTML = """<!DOCTYPE html>
<html>
  <body>
    <script>
      window.video = {
        id: '304645',
        filename: '',
        timestamps: [],
      };
      window.canPlayFHD = true;
      window.masterPlaylist = {
        params: {
          'token': 'mastertoken',
          'expires': '1799492226',
          'url': 'https://vixcloud.cc/playlist/304645'
        }
      };
    </script>
    <script>
      window.downloadUrl = 'https://vixcloud.cc/download/304645?token=dl';
    </script>
  </body>
</html>
"""


class FakeResponse:
    def __init__(self, text: str = "", status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise HTTPError(f"{self.status_code} Forbidden")


class FakeClient:
    def __init__(self, headers=None):
        # Snapshot the headers at call time: VideoSource mutates self.headers.
        self.headers = dict(headers or {})
        self.gets: list[str] = []

    def get(self, url):
        self.gets.append(str(url))
        if "/anime/" in str(url) or "/embed-url/" in str(url):
            return FakeResponse(EMBED_PAGE_HTML)
        return FakeResponse(EMBED_HTML)


class TestVideoSourceAnimeEmbed(unittest.TestCase):
    def _run(self, prefer_mp4: bool):
        clients: list[FakeClient] = []

        def factory(headers=None):
            client = FakeClient(headers)
            clients.append(client)
            return client

        with (
            mock.patch.object(vixcloud, "create_client_curl", factory),
            mock.patch.object(vixcloud, "create_client", factory),
            mock.patch.object(vixcloud, "get_userAgent", return_value="test-agent"),
        ):
            source = vixcloud.VideoSourceAnime("https://www.animeunity.co")
            result = source.get_embed(
                5987,
                prefer_mp4,
                video_id=5987,
                anime_id=1469,
                anime_slug="naruto",
            )

        return source, result, clients

    def _embed_client(self, clients):
        for client in clients:
            if any("vixcloud.cc/embed/" in url for url in client.gets):
                return client
        self.fail("no request was made to the vixcloud embed URL")

    def test_embed_request_sends_embed_host_referer(self):
        source, result, clients = self._run(prefer_mp4=True)

        self.assertIsNotNone(result)
        # Regression: vixcloud.cc answers 403 without a Referer.
        self.assertEqual(
            self._embed_client(clients).headers.get("referer"),
            "https://vixcloud.cc/",
        )

    def test_hls_playlist_is_built_from_master_playlist(self):
        source, _, _ = self._run(prefer_mp4=False)

        self.assertIsNotNone(source.master_playlist)
        self.assertTrue(
            source.master_playlist.startswith(
                "https://vixcloud.cc/playlist/304645?"
            )
        )
        self.assertIn("token=mastertoken", source.master_playlist)
        self.assertIn("expires=1799492226", source.master_playlist)
        self.assertIn("h=1", source.master_playlist)

    def test_mp4_download_url_is_extracted(self):
        source, _, _ = self._run(prefer_mp4=True)

        self.assertEqual(
            source.src_mp4, "https://vixcloud.cc/download/304645?token=dl"
        )
        self.assertIsNone(source.master_playlist)

    def test_embed_403_returns_none_instead_of_raising(self):
        class ForbiddenClient(FakeClient):
            def get(self, url):
                self.gets.append(str(url))
                if "/anime/" in str(url) or "/embed-url/" in str(url):
                    return FakeResponse(EMBED_PAGE_HTML)
                return FakeResponse("Forbidden", status_code=403)

        clients: list[FakeClient] = []

        def factory(headers=None):
            client = ForbiddenClient(headers)
            clients.append(client)
            return client

        with (
            mock.patch.object(vixcloud, "create_client_curl", factory),
            mock.patch.object(vixcloud, "create_client", factory),
            mock.patch.object(vixcloud, "get_userAgent", return_value="test-agent"),
        ):
            source = vixcloud.VideoSourceAnime("https://www.animeunity.co")
            self.assertIsNone(
                source.get_embed(
                    5987,
                    prefer_mp4=False,
                    video_id=5987,
                    anime_id=1469,
                    anime_slug="naruto",
                )
            )

        self.assertIsNone(source.master_playlist)


if __name__ == "__main__":
    unittest.main()
