# 23.10.26 - AnimeWorld video source

from __future__ import annotations

import logging

from StreamingCommunity.services.animeworld.client import AnimeWorldClient

logger = logging.getLogger(__name__)


class VideoSource:
    """Resolve an AnimeWorld episode to its direct MP4 URL.

    Kept as a small compatibility wrapper for callers that used the old
    ``player.sweetpixel.VideoSource`` API.  New code normally lets
    ``ScrapSerie.get_video_url`` reuse the scraper's authenticated client.
    """

    def __init__(
        self,
        site_url: str,
        episode_data=None,
        session_id: str | None = None,
        csrf_token: str | None = None,
    ):
        self.site_url = str(site_url).rstrip("/")
        self.episode_data = episode_data
        self.session_id = session_id
        self.csrf_token = csrf_token
        self.client = AnimeWorldClient(self.site_url)

    def get_playlist(self, token: str | None = None) -> str | None:
        token = token or getattr(self.episode_data, "token", None)
        if token is None and self.episode_data is not None:
            token = getattr(self.episode_data, "id", None)
        if not token:
            logger.warning("No AnimeWorld episode token supplied")
            return None

        try:
            info = self.client.episode_info(str(token))
            url = info.get("grabber") or info.get("download")
            return str(url).strip() if url else None
        except Exception as exc:
            logger.warning("AnimeWorld video source failed for %s: %s", token, exc)
            return None

    def close(self) -> None:
        self.client.close()
