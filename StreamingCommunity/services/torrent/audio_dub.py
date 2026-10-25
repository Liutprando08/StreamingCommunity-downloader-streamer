# 2026

import os
import re
import logging
import tempfile
from typing import Optional


# External library
from rich.prompt import Prompt


# Internal utilities
from StreamingCommunity.utils import TVShowManager, config_manager, os_manager
from StreamingCommunity.services._base import Entries
from StreamingCommunity.torrent.muxer import TorrentMuxer
from StreamingCommunity.utils.console.shared import console


# Variable
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


def search_audio_sources(query: str) -> list[Entries]:
    """
    Search StreamingCommunity for a title and return the raw results.

    Non-interactive (no terminal table, no stdin): used by the TUI, which
    renders its own picker and cannot block on the rich prompt.
    """
    from StreamingCommunity.services.streamingcommunity import entries_manager as _sc_em
    from StreamingCommunity.services.streamingcommunity import (
        title_search as sc_title_search,
    )

    _sc_em.clear()
    sc_title_search(query)
    return list(_sc_em.media_list)


def _display_results(entries: list[Entries]) -> Optional[Entries]:
    """Display search results and let the user pick one (CLI only)."""
    if not entries:
        return None

    table_show_manager = TVShowManager()
    column_info = {
        "Index": {"color": "red"},
        "Name": {"color": "magenta"},
        "Type": {"color": "yellow"},
        "Year": {"color": "cyan"},
    }
    table_show_manager.add_column(column_info)

    for i, entry in enumerate(entries):
        table_show_manager.add_tv_show(
            {
                "Index": str(i),
                "Name": str(getattr(entry, "name", "N/A")),
                "Type": str(getattr(entry, "type", "N/A")),
                "Year": str(getattr(entry, "year", "N/A")),
            }
        )

    last_command = table_show_manager.run(
        force_int_input=True, max_int_input=len(entries)
    )
    table_show_manager.clear()

    if last_command is None or last_command.lower() in ("q", "quit"):
        return None

    try:
        idx = int(last_command)
        if 0 <= idx < len(entries):
            return entries[idx]
    except (ValueError, IndexError):
        pass

    console.print("[red]Invalid selection")
    return None


def download_streaming_audio(
    entry: Entries,
    base_dir: Optional[str] = None,
    season: Optional[int] = None,
    episode: Optional[int] = None,
) -> Optional[str]:
    """
    Download content from StreamingCommunity via HLS_Downloader.
    Audio-only mode first, falls back to full download if it fails.
    Returns path to the downloaded file on success.
    """
    from StreamingCommunity.services.streamingcommunity.downloader import (
        _get_playlist_url,
        _get_vidxgo_headers,
    )
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

    console.print(
        f"[cyan]Resolving playlist for: [yellow]{getattr(entry, 'name', 'unknown')}"
    )

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
        headers=_get_vidxgo_headers(),
    ).start()

    if result and os.path.isfile(output_path):
        return output_path

    # Fallback: full download
    console.print("[yellow]Audio-only download failed, trying full download...")
    result = HLS_Downloader(
        m3u8_url=playlist_url,
        output_path=output_path,
        audio_only=False,
        headers=_get_vidxgo_headers(),
    ).start()

    if result and os.path.isfile(output_path):
        return output_path

    console.print("[red]StreamingCommunity download failed")
    return None


def mux_italian_audio(
    torrent_video_path: str, audio_path: str
) -> Optional[str]:
    """
    Mux ``audio_path`` onto ``torrent_video_path`` as an Italian track.

    Produces ``<base>_ita.<ext>`` next to the torrent video, removes the
    temporary audio and (only after validating the output with ffprobe) the
    original torrent video. Returns the dubbed path or None.
    """
    if not torrent_video_path or not os.path.isfile(torrent_video_path):
        return None
    if not audio_path or not os.path.isfile(audio_path):
        return None

    torrent_dir = os.path.dirname(torrent_video_path)
    torrent_base = os.path.splitext(os.path.basename(torrent_video_path))[0]
    extension_output = _get_extension_output()
    dubbed_path = os.path.join(torrent_dir, f"{torrent_base}_ita.{extension_output}")

    muxer = TorrentMuxer()
    result = muxer.mux_video_audio(torrent_video_path, audio_path, dubbed_path)

    # Validate the mux before touching the only copy of the original. A
    # killed ffmpeg used to leave a partial file behind, and this function
    # then deleted the good torrent video.
    valid = False
    if result and os.path.isfile(result):
        try:
            streams = muxer.detect_streams(result)
            valid = bool(streams.get("video")) and bool(streams.get("audio"))
        except Exception as e:
            log.warning("Could not validate dubbed output %s: %s", result, e)

    if result and not valid:
        console.print(f"[red]Dubbed output failed validation: {result}")
        try:
            os.remove(result)
        except OSError:
            pass
        result = None

    # Always drop the temporary streaming download.
    try:
        os.remove(audio_path)
        temp_dir = os.path.dirname(audio_path)
        if os.path.isdir(temp_dir) and not os.listdir(temp_dir):
            os.rmdir(temp_dir)
    except Exception as e:
        log.debug("Cleanup failed: %s", e)

    # Only remove the original once the dubbed file has been validated.
    if valid and result and os.path.isfile(result):
        try:
            os.remove(torrent_video_path)
        except Exception as e:
            log.debug("Failed to remove original: %s", e)

    return result


def dub_audio_from_source(
    select_title, torrent_video_path: str, source_entry: Entries
) -> Optional[str]:
    """
    Non-interactive dub: download the Italian audio for ``source_entry`` and
    mux it onto ``torrent_video_path``.

    Used by the TUI, where the user has already picked the StreamingCommunity
    source before the download was enqueued.
    """
    if not torrent_video_path or not os.path.isfile(torrent_video_path):
        return None
    if source_entry is None:
        return None

    season, episode = _parse_season_episode(str(getattr(select_title, "name", "")))
    is_series = str(getattr(select_title, "type", "")).lower() in (
        "tv",
        "serie",
        "show",
    )

    streaming_path = download_streaming_audio(
        source_entry,
        base_dir=os.path.dirname(torrent_video_path),
        season=season if is_series else None,
        episode=episode if is_series else None,
    )
    if not streaming_path:
        return None

    return mux_italian_audio(torrent_video_path, streaming_path)


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
        "\n[yellow]Search StreamingCommunity for",
        default=default_query,
    )
    if not query or not query.strip():
        console.print("[red]Empty query, skipping audio dub")
        return None

    console.print(f"\n[cyan]Searching StreamingCommunity for: [yellow]{query}")

    entries = search_audio_sources(query)
    if not entries:
        console.print("[yellow]No results found on StreamingCommunity")
        return None

    picked = _display_results(entries)
    if not picked:
        console.print("[yellow]Selection cancelled")
        return None

    console.print(f"[cyan]Selected: [yellow]{getattr(picked, 'name', 'unknown')}")

    return dub_audio_from_source(select_title, torrent_video_path, picked)
