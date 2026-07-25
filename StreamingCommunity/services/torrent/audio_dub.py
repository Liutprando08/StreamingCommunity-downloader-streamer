# 2026

import os
import re
import logging
import tempfile
from typing import Optional


# External library
from rich.console import Console
from rich.prompt import Prompt


# Internal utilities
from StreamingCommunity.utils import TVShowManager, config_manager, os_manager
from StreamingCommunity.services._base import EntriesManager, Entries
from StreamingCommunity.torrent.muxer import TorrentMuxer


# Variable
console = Console()
msg = Prompt()
log = logging.getLogger(__name__)


def _get_extension_output():
    return config_manager.config.get("PROCESS", "extension")


def _parse_season_episode(title: str) -> tuple:
    """Parse season and episode numbers from a torrent title.

    Returns (season, episode) tuple. Returns (None, None) if not found.
    """
    title_lower = title.lower()

    season = None
    episode = None

    season_match = re.search(r"s(\d{1,2})", title_lower)
    if season_match:
        season = int(season_match.group(1))

    episode_match = re.search(r"e(\d{1,3})", title_lower)
    if episode_match:
        episode = int(episode_match.group(1))

    if season is None:
        season_match = re.search(r"season\s*(\d{1,2})", title_lower)
        if season_match:
            season = int(season_match.group(1))

    if episode is None:
        episode_match = re.search(r"episode\s*(\d{1,3})", title_lower)
        if episode_match:
            episode = int(episode_match.group(1))

    if season is None and episode is None:
        ep_match = re.search(r"(\d{1,3})x(\d{1,3})", title_lower)
        if ep_match:
            season = int(ep_match.group(1))
            episode = int(ep_match.group(2))

    return season, episode


def _search_streamingcommunity(query: str) -> int:
    """
    Search StreamingCommunity for a title by name.
    Returns number of results found. Entries are in _sc_entries.
    """
    from StreamingCommunity.services.streamingcommunity import title_search as sc_title_search

    return sc_title_search(query)


def _display_results(entries_manager: EntriesManager) -> Optional[Entries]:
    """Display search results and let user pick one."""
    if not entries_manager.media_list:
        return None

    table_show_manager = TVShowManager()
    column_info = {
        "Index": {"color": "red"},
        "Name": {"color": "magenta"},
        "Type": {"color": "yellow"},
        "Year": {"color": "cyan"},
    }
    table_show_manager.add_column(column_info)

    for i, entry in enumerate(entries_manager.media_list):
        table_show_manager.add_tv_show({
            "Index": str(i),
            "Name": str(getattr(entry, "name", "N/A")),
            "Type": str(getattr(entry, "type", "N/A")),
            "Year": str(getattr(entry, "year", "N/A")),
        })

    last_command = table_show_manager.run(force_int_input=True, max_int_input=len(entries_manager.media_list))
    table_show_manager.clear()

    if last_command is None or last_command.lower() in ("q", "quit"):
        return None

    try:
        idx = int(last_command)
        if 0 <= idx < len(entries_manager.media_list):
            return entries_manager.media_list[idx]
    except (ValueError, IndexError):
        pass

    console.print("[red]Invalid selection")
    return None


def _download_streaming_content(entry: Entries, base_dir: str = None, season: int = None, episode: int = None) -> Optional[str]:
    """
    Download content from StreamingCommunity via HLS_Downloader.
    Audio-only mode first, falls back to full download if it fails.
    Returns path to the downloaded file on success.
    """
    from StreamingCommunity.services.streamingcommunity.downloader import _get_playlist_url
    from StreamingCommunity.core.downloader import HLS_Downloader

    imdb_id = getattr(entry, "imdb_id", None)
    if not imdb_id:
        console.print("[red]No IMDB ID available for this entry")
        return None

    is_series = str(getattr(entry, "type", "")).lower() in ("tv", "serie", "show")
    if is_series:
        if season is None:
            season = 1
        if episode is None:
            episode = 1

    console.print(f"[cyan]Resolving playlist for: [yellow]{getattr(entry, 'name', 'unknown')}")

    playlist_url = _get_playlist_url(imdb_id, is_series, season, episode)
    if not playlist_url:
        console.print("[red]Could not resolve streaming playlist")
        return None

    temp_dir = os.path.join(base_dir or tempfile.gettempdir(), ".sc_audio_dub")
    os.makedirs(temp_dir, exist_ok=True)

    extension_output = _get_extension_output()
    safe_name = os_manager.get_sanitize_file(getattr(entry, "name", "stream"))
    output_filename = f"{safe_name}_sc.{extension_output}"
    output_path = os.path.join(temp_dir, output_filename)

    # Try audio-only first
    console.print("[cyan]Downloading audio only from StreamingCommunity...")
    result = HLS_Downloader(
        m3u8_url=playlist_url,
        output_path=output_path,
        audio_only=True,
    ).start()

    if result and result[0] and os.path.isfile(result[0]):
        return result[0]

    # Fallback: full download
    console.print("[yellow]Audio-only download failed, trying full download...")
    result = HLS_Downloader(
        m3u8_url=playlist_url,
        output_path=output_path,
        audio_only=False,
    ).start()

    if result and result[0] and os.path.isfile(result[0]):
        return result[0]

    console.print("[red]StreamingCommunity download failed")
    return None


def prompt_audio_dub(select_title, torrent_video_path: str) -> Optional[str]:
    """
    After torrent download, prompt user for Italian audio dubbing.

    Parameters:
        select_title: The torrent Entries object (has .name, .type, etc.)
        torrent_video_path: Path to the downloaded torrent video file.

    Returns:
        str: Path to the dubbed file, or None if declined/failed.
    """
    if not torrent_video_path or not os.path.isfile(torrent_video_path):
        return None

    from StreamingCommunity.torrent.config import TorrentConfig
    torrent_config = TorrentConfig(config_manager)

    if torrent_config.auto_mux:
        answer = "y"
    else:
        answer = msg.ask(
            "\n[yellow]Download Italian audio from StreamingCommunity?",
            choices=["y", "n"],
            default="n",
        )

    if answer.lower() != "y":
        return None

    default_query = str(getattr(select_title, "name", "")).strip()
    query = msg.ask(
        f"\n[yellow]Search StreamingCommunity for",
        default=default_query,
    )
    if not query or not query.strip():
        console.print("[red]Empty query, skipping audio dub")
        return None

    console.print(f"\n[cyan]Searching StreamingCommunity for: [yellow]{query}")

    from StreamingCommunity.services.streamingcommunity import entries_manager as _sc_em
    from StreamingCommunity.services.streamingcommunity import title_search as sc_title_search

    _sc_em.clear()
    count = sc_title_search(query)

    if count == 0:
        console.print("[yellow]No results found on StreamingCommunity")
        return None

    picked = _display_results(_sc_em)
    if not picked:
        console.print("[yellow]Selection cancelled")
        return None

    console.print(f"[cyan]Selected: [yellow]{getattr(picked, 'name', 'unknown')}")

    season, episode = _parse_season_episode(str(getattr(select_title, "name", "")))
    is_series = str(getattr(select_title, "type", "")).lower() in ("tv", "serie", "show")

    streaming_path = _download_streaming_content(
        picked,
        base_dir=os.path.dirname(torrent_video_path),
        season=season if is_series else None,
        episode=episode if is_series else None,
    )
    if not streaming_path:
        return None

    torrent_dir = os.path.dirname(torrent_video_path)
    torrent_base = os.path.splitext(os.path.basename(torrent_video_path))[0]
    extension_output = _get_extension_output()
    dubbed_filename = f"{torrent_base}_ita.{extension_output}"
    dubbed_path = os.path.join(torrent_dir, dubbed_filename)

    muxer = TorrentMuxer()
    result = muxer.mux_video_audio(torrent_video_path, streaming_path, dubbed_path)

    try:
        os.remove(streaming_path)
        temp_dir = os.path.dirname(streaming_path)
        if os.path.isdir(temp_dir) and not os.listdir(temp_dir):
            os.rmdir(temp_dir)
    except Exception as e:
        log.debug("Cleanup failed: %s", e)

    if result and os.path.isfile(torrent_video_path):
        try:
            os.remove(torrent_video_path)
        except Exception as e:
            log.debug("Failed to remove original: %s", e)

    return result
