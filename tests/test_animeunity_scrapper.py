from __future__ import annotations

import unittest
from unittest import mock

from StreamingCommunity.services.animeunity import scrapper


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeClient:
    def __init__(self, pages: dict[int, dict]):
        self.pages = pages
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, params=None):
        params = params or {}
        self.calls.append((str(url), dict(params)))
        return FakeResponse(self.pages[int(params.get("start", 0))])


def episode(episode_id: int, number: str, videos: list[dict]) -> dict:
    return {
        "id": episode_id,
        "number": number,
        "seq_number_start": int(number),
        "seq_number_end": int(number),
        "videos": videos,
    }


class TestAnimeUnityScrapper(unittest.TestCase):
    def _make_scraper(self):
        pages = {
            0: {
                "episodes": [
                    episode(
                        1,
                        "1",
                        [
                            {"id": 111, "language": "ita", "is_hidden": False},
                            {"id": 112, "language": "jpn", "is_hidden": False},
                        ],
                    ),
                    episode(
                        2,
                        "2",
                        [{"id": 113, "language": "jpn", "is_hidden": False}],
                    ),
                ],
                "start": 0,
                "tab_size": 2,
                "total": 3,
            },
            2: {
                "episodes": [
                    episode(
                        3,
                        "3",
                        [{"id": 114, "language": "jpn", "is_hidden": False}],
                    )
                ],
                "start": 2,
                "tab_size": 2,
                "total": 3,
            },
        }
        client = FakeClient(pages)
        patcher = mock.patch.object(
            scrapper, "create_client_curl", return_value=client
        )
        self.addCleanup(patcher.stop)
        patcher.start()

        scraper = scrapper.ScrapeSerieAnime("https://animeunity.test")
        scraper.setup(None, 1469, "naruto")
        return scraper, client

    def test_fetches_all_episodes_using_paginated_api(self):
        scraper, client = self._make_scraper()

        self.assertEqual(scraper.get_count_episodes(), 3)
        self.assertEqual(
            [params["start"] for _, params in client.calls],
            [0, 2],
        )
        self.assertTrue(
            all("/api/anime/1469/episodes" in url for url, _ in client.calls)
        )

    def test_prefers_italian_video_id(self):
        scraper, _ = self._make_scraper()

        first = scraper.selectEpisode(1, 0)
        second = scraper.selectEpisode(1, 1)

        self.assertIsNotNone(first)
        self.assertEqual(first.video_id, 111)
        self.assertEqual(second.video_id, 113)


if __name__ == "__main__":
    unittest.main()
