from __future__ import annotations

from typing import Callable

from StreamingCommunity.utils import config_manager

from .dash import DASH_Downloader
from .hls import HLS_Downloader
from .ism import ISM_Downloader
from .mega import MEGA_Downloader
from .mp4 import MP4_Downloader
from .ytdlp import YTDLP_Downloader

__all__ = [
    "DASH_Downloader",
    "HLS_Downloader",
    "ISM_Downloader",
    "MEGA_Downloader",
    "MP4_Downloader",
    "YTDLP_Downloader",
    "download_hls",
    "download_mp4",
]


def _engine() -> str:
    """Return the configured download engine for the migrated services."""
    try:
        value = config_manager.config.get(
            "DOWNLOAD", "engine", default="ytdlp"
        )
    except (ValueError, KeyError):
        return "ytdlp"
    return str(value or "ytdlp").strip().lower()


def download_hls(
    *,
    url: str,
    output_path: str | None = None,
    headers: dict[str, str] | None = None,
    audio_only: bool = False,
    playlist_resolver: Callable[[], str | None] | None = None,
):
    """Download an HLS stream with yt-dlp (legacy engine via ``DOWNLOAD.engine``)."""
    if _engine() == "nm3u8":
        return HLS_Downloader(
            m3u8_url=url,
            output_path=output_path,
            headers=headers,
            audio_only=audio_only,
            playlist_resolver=playlist_resolver,
        ).start()

    return YTDLP_Downloader(
        url=url,
        output_path=output_path,
        headers=headers,
        audio_only=audio_only,
        playlist_resolver=playlist_resolver,
    ).start()


def download_mp4(
    *,
    url: str,
    output_path: str,
    headers: dict[str, str] | None = None,
):
    """Download a progressive (MP4) URL with yt-dlp."""
    if _engine() == "nm3u8":
        return MP4_Downloader(
            url=url,
            path=output_path,
            headers_=headers,
        )

    return YTDLP_Downloader(
        url=url,
        output_path=output_path,
        headers=headers,
    ).start()
