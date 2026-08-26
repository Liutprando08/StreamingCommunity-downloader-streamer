# 21.08.26


from __future__ import annotations

import os

# External library
import yt_dlp
from rich.prompt import Prompt
from yt_dlp.utils import DownloadError, ExtractorError

from StreamingCommunity.services._base import Entries, site_constants

# Internal utilities
from StreamingCommunity.utils import config_manager, os_manager, start_message
from StreamingCommunity.utils.console.shared import console

# Variables
msg = Prompt()
extension_output = config_manager.config.get("PROCESS", "extension")
SKIP_DOWNLOAD = config_manager.config.get_bool("DOWNLOAD", "skip_download")
CUSTOM_FORMAT = config_manager.config.get("YOUTUBE", "format", default="")
MAX_HEIGHT = config_manager.config.get(
    "YOUTUBE", "max_height", data_type=int, default=0
)

DEFAULT_FORMAT = "bv*+ba/b"


def _build_format(max_height: int | None = None) -> str:
    """Compose a yt-dlp format selector, optionally capping the video height."""
    if max_height:
        return f"bv*[height<={max_height}]+ba/b[height<={max_height}]"
    return DEFAULT_FORMAT


def _get_available_heights(url: str | None) -> list[int]:
    """Return the distinct available video heights for a URL, sorted descending."""
    try:
        with yt_dlp.YoutubeDL(
            {"quiet": True, "no_warnings": True, "skip_download": True}  # type: ignore[reportArgumentType]
        ) as ydl:
            infos = ydl.extract_info(url, download=False)  # type: ignore[reportArgumentType]

    except ExtractorError as e:
        console.print(f"[yellow]Could not fetch available formats: {e}")
        return []

    heights = set()
    for fmt in infos.get("formats") or []:
        if fmt.get("vcodec") != "none" and fmt.get("height"):
            heights.add(int(fmt["height"]))

    return sorted(heights, reverse=True)


def _resolve_format(url: str | None) -> str | None:
    """
    Determine the yt-dlp format selector to use for the download.

    Priority: custom format string from config > max_height cap from config >
    interactive quality menu.
    """
    if CUSTOM_FORMAT:
        return CUSTOM_FORMAT

    if MAX_HEIGHT > 0:
        return _build_format(MAX_HEIGHT)

    heights = _get_available_heights(url)
    if not heights:
        return _build_format()


def download_film(select_title: Entries) -> tuple[str | None, bool] | None:
    start_message()
    console.print(
        f"\n[yellow]Download: [red]{site_constants.SITE_NAME} → [cyan]{select_title.name} \n"
    )
    # Define output path
    if select_title.name is not None:
        file_name = f"{os_manager.get_sanitize_file(select_title.name, select_title.year)}.{extension_output}"
    output_path = os_manager.get_sanitize_path(
        os.path.join(site_constants.MOVIE_FOLDER, file_name)
    )

    if SKIP_DOWNLOAD:
        console.print(
            "[yellow]Download skipped due to configuration. Returning intended file path."
        )
        return output_path, False

    # Ensure the destination folder exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Resolve video quality
    format_selection = _resolve_format(select_title.url)

    ydl_opts = {
        "format": format_selection,
        # yt-dlp appends the container extension itself; escape '%' for the template engine
        "outtmpl": os.path.splitext(output_path)[0].replace("%", "%%"),
        "merge_output_format": extension_output,
        "noplaylist": True,
        "quiet": False,
        "no_warnings": True,
        "retries": config_manager.config.get(
            "DOWNLOAD", "retry_count", data_type=int, default=30
        ),
        "concurrent_fragment_downloads": config_manager.config.get(
            "DOWNLOAD", "thread_count", data_type=int, default=8
        ),
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[reportArgumentType]
            ydl.download([select_title.url])  # type: ignore[reportArgumentType]

    except DownloadError as e:
        console.print(f"[red]Error downloading video: {e}")
        return None, True

    console.print("[green]Download completed.")
    return output_path, False
