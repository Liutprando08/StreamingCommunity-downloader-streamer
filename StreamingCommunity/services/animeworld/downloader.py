# 23.10.26 - AnimeWorld downloader / streamer

from __future__ import annotations

import os

# External library
from rich.prompt import Prompt

# Downloader
from StreamingCommunity.core.downloader import MP4_Downloader

# Internal utilities
from StreamingCommunity.services._base import Entries, site_constants
from StreamingCommunity.services._base.tv_display_manager import (
    dynamic_format_number,
    manage_selection,
)
from StreamingCommunity.utils import os_manager, start_message
from StreamingCommunity.utils.console.shared import console
from StreamingCommunity.utils.http_client import get_userAgent

# Logic
from .scrapper import Episode, ScrapSerie, new_scraper

msg = Prompt()


def _build_scraper(
    select_title: Entries | None = None, scrape_serie=None
) -> ScrapSerie:
    if scrape_serie is not None:
        return scrape_serie
    if select_title is None:
        raise ValueError("AnimeWorld title is missing")

    media_url = (
        getattr(select_title, "slug", None)
        or getattr(select_title, "url", None)
        or getattr(select_title, "name", None)
    )
    return new_scraper(media_url)


def _video_headers() -> dict[str, str]:
    return {
        "User-Agent": get_userAgent(),
        "Referer": f"{site_constants.FULL_URL}/",
    }


def download_film(select_title: Entries):
    """Download the first (and normally only) episode of an AnimeWorld film."""
    start_message()
    try:
        scrape_serie = _build_scraper(select_title)
    except Exception as exc:
        console.print(f"[red]AnimeWorld: unable to open title: {exc}")
        return None

    scrape_serie.is_series = False
    scrape_serie.movie_year = getattr(select_title, "year", None)
    episode = scrape_serie.selectEpisode(1, 0)
    if episode is None:
        console.print(f"[red]No episodes found for {select_title.name}")
        return None

    result = download_episode(episode, 1, 1, scrape_serie)
    if not result or result[0] is None:
        return None
    return result


def download_episode(
    obj_episode: Episode,
    index_season_selected: int,
    index_episode_selected: int,
    scrape_serie: ScrapSerie,
    video_source=None,
):
    """Download one AnimeWorld episode as a direct MP4."""
    if obj_episode is None:
        console.print("[red]Error: No episode available for this title")
        return None, False

    start_message()
    console.print(
        f"\n[yellow]Download: [red]{site_constants.SITE_NAME} → "
        f"[cyan]{scrape_serie.get_name()} "
        f"([cyan]E{obj_episode.number}) \n"
    )

    mp4_link = scrape_serie.get_video_url(obj_episode)
    if not mp4_link:
        console.print("[red]Error: No MP4 URL found")
        return None, False

    if getattr(scrape_serie, "is_series", True):
        mp4_name = (
            f"{scrape_serie.get_name()}_EP_"
            f"{dynamic_format_number(str(obj_episode.number))}.mp4"
        )
        mp4_path = os_manager.get_sanitize_path(
            os.path.join(site_constants.ANIME_FOLDER, scrape_serie.get_name())
        )
    else:
        mp4_name = f"{scrape_serie.get_name() or 'film'}.mp4"
        year = getattr(scrape_serie, "movie_year", None)
        if year:
            mp4_name = (
                f"{os_manager.get_sanitize_file(scrape_serie.get_name() or 'film', str(year))}"
                ".mp4"
            )
        mp4_path = os_manager.get_sanitize_path(site_constants.MOVIE_FOLDER)

    os_manager.create_path(mp4_path)
    path, kill_handler = MP4_Downloader(
        url=str(mp4_link).strip(),
        path=os.path.join(mp4_path, mp4_name),
        referer=f"{site_constants.FULL_URL}/",
        headers_=_video_headers(),
    )

    return path, kill_handler


def download_series(
    select_title: Entries,
    season_selection: str | None = None,
    episode_selection: str | None = None,
    scrape_serie=None,
):
    """Download selected episodes from the single AnimeWorld season."""
    start_message()
    try:
        scrape_serie = _build_scraper(select_title, scrape_serie)
    except Exception as exc:
        console.print(f"[red]AnimeWorld: unable to open title: {exc}")
        return None

    episode_count = scrape_serie.get_count_episodes()
    if not episode_count:
        console.print("[red]Error: No episodes found for this title")
        return None

    console.print(f"\n[green]Episodes count: [red]{episode_count}")

    if episode_selection is None:
        last_command = msg.ask(
            "\n[cyan]Insert media [red]index [yellow]or [red]* [cyan]to download all media "
            "[yellow]or [red]1-2 [cyan]or [red]3-* [cyan]for a range of media"
        )
    else:
        last_command = episode_selection
        console.print(
            f"\n[cyan]Using provided episode selection: [yellow]{episode_selection}"
        )

    selected = manage_selection(last_command, episode_count)
    if not selected:
        return None

    last_path = None
    kill_handler = False
    for episode_number in selected:
        if kill_handler:
            break
        episode = scrape_serie.selectEpisode(1, episode_number - 1)
        last_path, kill_handler = download_episode(
            episode, 1, episode_number, scrape_serie
        )
        if last_path is None:
            return None

    return last_path


def stream_film(select_title: Entries):
    """Stream the first (and normally only) episode of an AnimeWorld film."""
    start_message()
    try:
        scrape_serie = _build_scraper(select_title)
    except Exception as exc:
        console.print(f"[red]AnimeWorld: unable to open title: {exc}")
        return None

    scrape_serie.is_series = False
    scrape_serie.movie_year = getattr(select_title, "year", None)
    episode = scrape_serie.selectEpisode(1, 0)
    if episode is None:
        console.print(f"[red]No episodes found for {select_title.name}")
        return None

    return stream_episode(episode, 1, 1, scrape_serie)


def stream_episode(
    obj_episode: Episode,
    index_season_selected: int,
    index_episode_selected: int,
    scrape_serie: ScrapSerie,
    video_source=None,
):
    """Stream one AnimeWorld episode in the configured media player."""
    from StreamingCommunity.streaming.session import stream_content

    if obj_episode is None:
        console.print("[red]Error: No episode available for this title")
        return None

    start_message()
    console.print(
        f"\n[yellow]Streaming: [red]{site_constants.SITE_NAME} → "
        f"[cyan]{scrape_serie.get_name()} [white]\\ "
        f"[magenta]{obj_episode.name} "
        f"([cyan]S{index_season_selected}E{index_episode_selected})\n"
    )

    mp4_link = scrape_serie.get_video_url(obj_episode)
    if not mp4_link:
        console.print("[red]Error: No MP4 URL found")
        return None

    player = os.environ.get("STREAMING_PLAYER") or None
    port = int(os.environ.get("STREAMING_PORT", "0"))

    stream_content(
        playlist_url=mp4_link,
        headers=_video_headers(),
        preferred_player=player,
        port=port,
        direct_media=True,
    )

    return mp4_link


def stream_series(
    select_title: Entries,
    season_selection: str | None = None,
    episode_selection: str | None = None,
    scrape_serie=None,
):
    """Stream selected AnimeWorld episodes one after another."""
    start_message()
    try:
        scrape_serie = _build_scraper(select_title, scrape_serie)
    except Exception as exc:
        console.print(f"[red]AnimeWorld: unable to open title: {exc}")
        return None

    episode_count = scrape_serie.get_count_episodes()
    if not episode_count:
        console.print("[red]Error: No episodes found for this title")
        return None

    if episode_selection is None:
        last_command = msg.ask(
            "\n[cyan]Insert media [red]index [yellow]or [red]* [cyan]to stream all media "
            "[yellow]or [red]1-2 [cyan]or [red]3-* [cyan]for a range of media"
        )
    else:
        last_command = episode_selection
        console.print(
            f"\n[cyan]Using provided episode selection: [yellow]{episode_selection}"
        )

    selected = manage_selection(last_command, episode_count)
    if not selected:
        return None

    for episode_number in selected:
        episode = scrape_serie.selectEpisode(1, episode_number - 1)
        if stream_episode(episode, 1, episode_number, scrape_serie) is None:
            return None

    return True
