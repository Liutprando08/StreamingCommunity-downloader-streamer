# 22.06.26 - Rewritten for streaming-community.fans (vixsrc.to API)

from __future__ import annotations

import os
import os as _os
from typing import Any

# External library
from httpx import HTTPError
from rich.console import Console
from rich.prompt import Prompt

# Downloader
from StreamingCommunity.core.downloader import HLS_Downloader

# Player
from StreamingCommunity.player.vixcloud import VideoSource
from StreamingCommunity.services._base import Entries, site_constants
from StreamingCommunity.services._base.tv_display_manager import map_episode_title
from StreamingCommunity.services._base.tv_download_manager import (
    process_episode_download,
    process_season_selection,
)

# Internal utilities
from StreamingCommunity.utils import config_manager, os_manager, start_message
from StreamingCommunity.utils.http_client import create_client, get_userAgent

# Logic
from .scrapper import GetSerieInfo

# Variable
console = Console()
msg = Prompt()
extension_output = config_manager.config.get("PROCESS", "extension")
headers = {"user-agent": get_userAgent()}
VIXSRC_API = "https://vixsrc.to/api"


def _get_playlist_url(
    imdb_id: str | None,
    is_series: bool,
    season: int | None = None,
    episode: int | None = None,
) -> str | None:
    api_url = (
        f"{VIXSRC_API}/tv/{imdb_id}/{season}/{episode}?lang=it&ref=clone"
        if is_series
        else f"{VIXSRC_API}/movie/{imdb_id}?lang=it&ref=clone"
    )

    try:
        response = create_client(headers=headers).get(api_url)
        response.raise_for_status()
        data = response.json()
        embed_src = data.get("src")
        if not embed_src:
            console.print("[red]No embed src found in API response")
            return None
    except HTTPError as e:
        console.print(f"[red]Error fetching API: {e}")
        return None

    full_embed_url = f"https://vixsrc.to{embed_src}"

    vs = VideoSource("", is_series, None)
    vs.iframe_src = full_embed_url
    vs.get_content()
    return vs.get_playlist()


def download_film(select_title: Entries) -> tuple[str | None, Any] | None:
    start_message()
    console.print(
        f"\n[yellow]Download: [red]{site_constants.SITE_NAME} → [cyan]{select_title.name} \n"
    )

    imdb_id = getattr(select_title, "imdb_id", None)
    if not imdb_id:
        console.print("[red]No IMDB ID available for this title")
        return None

    master_playlist = _get_playlist_url(imdb_id, False)
    if master_playlist is None:
        console.print("[red]Error: No master playlist found")
        return None

    mp4_name = f"{os_manager.get_sanitize_file(select_title.name)}.{extension_output}"
    mp4_path = os.path.join(
        site_constants.MOVIE_FOLDER, mp4_name.replace(f".{extension_output}", "")
    )

    return HLS_Downloader(
        m3u8_url=master_playlist, output_path=os.path.join(mp4_path, mp4_name)
    ).start()


def download_episode(
    obj_episode, index_season_selected, index_episode_selected, scrape_serie
):
    start_message()
    console.print(
        f"\n[yellow]Download: [red]{site_constants.SITE_NAME} → [cyan]{scrape_serie.series_name} [white]\\ [magenta]{obj_episode.name} ([cyan]S{index_season_selected}E{index_episode_selected}) \n"
    )

    master_playlist = _get_playlist_url(
        scrape_serie.imdb_id, True, index_season_selected, index_episode_selected
    )
    if master_playlist is None:
        console.print("[red]Error: No master playlist found")
        return None, False

    mp4_name = f"{map_episode_title(scrape_serie.series_name, index_season_selected, index_episode_selected, obj_episode.name)}.{extension_output}"
    mp4_path = os.path.join(
        site_constants.SERIES_FOLDER,
        scrape_serie.series_name,
        f"S{index_season_selected}",
    )

    return HLS_Downloader(
        m3u8_url=master_playlist, output_path=os.path.join(mp4_path, mp4_name)
    ).start()


def download_series(
    select_season: Entries,
    season_selection: str | None = None,
    episode_selection: str | None = None,
    scrape_serie=None,
) -> None:
    start_message()
    imdb_id = getattr(select_season, "imdb_id", None)
    if not imdb_id:
        console.print("[red]No IMDB ID available for this series")
        return

    if scrape_serie is None:
        scrape_serie = GetSerieInfo(imdb_id, select_season.name)
        scrape_serie.getNumberSeason()
    seasons_count = len(scrape_serie.seasons_manager)

    def download_episode_callback(
        season_number: int, download_all: bool, episode_selection: str | None = None
    ):
        def download_video_callback(obj_episode, season_idx, episode_idx):
            return download_episode(obj_episode, season_idx, episode_idx, scrape_serie)

        process_episode_download(
            index_season_selected=season_number,
            scrape_serie=scrape_serie,
            download_video_callback=download_video_callback,
            download_all=download_all,
            episode_selection=episode_selection,
        )

    process_season_selection(
        scrape_serie=scrape_serie,
        seasons_count=seasons_count,
        season_selection=season_selection,
        episode_selection=episode_selection,
        download_episode_callback=download_episode_callback,
    )


def stream_film(select_title: Entries):
    from StreamingCommunity.streaming.session import stream_content

    start_message()
    console.print(
        f"\n[yellow]Streaming: [red]{site_constants.SITE_NAME} → [cyan]{select_title.name}\n"
    )

    imdb_id = getattr(select_title, "imdb_id", None)
    if not imdb_id:
        console.print("[red]No IMDB ID available for this title")
        return

    master_playlist = _get_playlist_url(imdb_id, False)
    if master_playlist is None:
        console.print("[red]Error: No master playlist found")
        return

    player = _os.environ.get("STREAMING_PLAYER") or None
    port = int(_os.environ.get("STREAMING_PORT", "0"))

    stream_content(
        playlist_url=master_playlist,
        headers={"User-Agent": get_userAgent()},
        preferred_player=player,
        port=port,
    )


def stream_episode(
    obj_episode, index_season_selected, index_episode_selected, scrape_serie
):
    from StreamingCommunity.streaming.session import stream_content

    start_message()
    console.print(
        f"\n[yellow]Streaming: [red]{site_constants.SITE_NAME} → [cyan]{scrape_serie.series_name} [white]\\ [magenta]{obj_episode.name} ([cyan]S{index_season_selected}E{index_episode_selected})\n"
    )

    master_playlist = _get_playlist_url(
        scrape_serie.imdb_id, True, index_season_selected, index_episode_selected
    )
    if master_playlist is None:
        console.print("[red]Error: No master playlist found")
        return

    player = _os.environ.get("STREAMING_PLAYER") or None
    port = int(_os.environ.get("STREAMING_PORT", "0"))

    stream_content(
        playlist_url=master_playlist,
        headers={"User-Agent": get_userAgent()},
        preferred_player=player,
        port=port,
    )


def stream_series(
    select_season: Entries,
    season_selection: str | None = None,
    episode_selection: str | None = None,
    scrape_serie=None,
):
    start_message()
    imdb_id = getattr(select_season, "imdb_id", None)
    if not imdb_id:
        console.print("[red]No IMDB ID available for this series")
        return

    if scrape_serie is None:
        scrape_serie = GetSerieInfo(imdb_id, select_season.name)
        scrape_serie.getNumberSeason()
    seasons_count = len(scrape_serie.seasons_manager)

    def stream_episode_callback(
        season_number: int, download_all: bool, episode_selection: str | None = None
    ):
        def stream_video_callback(obj_episode, season_idx, episode_idx):
            return stream_episode(obj_episode, season_idx, episode_idx, scrape_serie)

        process_episode_download(
            index_season_selected=season_number,
            scrape_serie=scrape_serie,
            download_video_callback=stream_video_callback,
            download_all=download_all,
            episode_selection=episode_selection,
        )

    process_season_selection(
        scrape_serie=scrape_serie,
        seasons_count=seasons_count,
        season_selection=season_selection,
        episode_selection=episode_selection,
        download_episode_callback=stream_episode_callback,
    )
