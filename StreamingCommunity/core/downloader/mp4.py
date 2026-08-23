# 09.06.24

from __future__ import annotations

import logging
import os
import signal
import threading
import time
from collections import deque
from functools import partial

import httpx2

# External libraries
from rich.console import Console
from rich.prompt import Prompt

from StreamingCommunity.core.processors.helper.kodi_nfo import (
    KODI_NFO_FILES,
    generate_kodi_metadata,
)
from StreamingCommunity.core.processors.helper.nfo import create_nfo
from StreamingCommunity.core.ui.bar_manager import DownloadBarManager
from StreamingCommunity.source.utils.tracker import context_tracker, download_tracker
from StreamingCommunity.utils import config_manager, internet_manager, os_manager

# Internal utilities
from StreamingCommunity.utils.http_client import create_client, get_userAgent

# Config
msg = Prompt()
console = Console()
REQUEST_VERIFY = config_manager.config.get_bool("REQUESTS", "verify")
CREATE_NFO_FILES = config_manager.config.get_bool(
    "PROCESS", "generate_nfo", default=False
)
SKIP_DOWNLOAD = config_manager.config.get_bool("DOWNLOAD", "skip_download")

logger = logging.getLogger(__name__)


class InterruptHandler:
    def __init__(self):
        self.interrupt_count = 0
        self.last_interrupt_time = 0
        self.kill_download = False
        self.force_quit = False


def signal_handler(signum, frame, interrupt_handler, original_handler):
    """Enhanced signal handler for multiple interrupt scenarios"""
    current_time = time.time()

    # Reset counter if more than 2 seconds have passed since last interrupt
    if current_time - interrupt_handler.last_interrupt_time > 2:
        interrupt_handler.interrupt_count = 0

    interrupt_handler.interrupt_count += 1
    interrupt_handler.last_interrupt_time = current_time

    if interrupt_handler.interrupt_count == 1:
        interrupt_handler.kill_download = True
        console.print(
            "\n[yellow]First interrupt received. Download will complete and save. Press Ctrl+C three times quickly to force quit."
        )

    elif interrupt_handler.interrupt_count >= 3:
        interrupt_handler.force_quit = True
        console.print("\n[red]Force quit activated. Saving partial download...")
        signal.signal(signum, original_handler)


def MP4_Downloader(
    url: str,
    path: str,
    referer: str | None = None,
    headers_: dict | None = None,
    show_final_info: bool = True,
    download_id: str | None = None,
    site_name: str | None = None,
):
    """
    Downloads an MP4 video with enhanced interrupt handling.
    - Single Ctrl+C: Completes download gracefully
    - Triple Ctrl+C: Saves partial download and exits
    """
    url = str(url).strip()
    path = os_manager.get_sanitize_path(path)

    # Get tracking IDs from context if not provided
    download_id = download_id or context_tracker.download_id
    site_name = site_name or context_tracker.site_name
    media_type = context_tracker.media_type or "Film"

    if SKIP_DOWNLOAD:
        console.print(
            "[yellow]Download skipped due to configuration. Returning intended file path."
        )
        return path, False

    if os.path.exists(path):
        console.print("[yellow]File already exists.")
        return path, False

    if not (url.lower().startswith("http://") or url.lower().startswith("https://")):
        logger.error(f"Invalid URL: {url}")
        console.print(f"[red]Invalid URL: {url}")
        return None, False

    # Start tracking in GUI
    if download_id:
        filename = os.path.basename(path)
        download_tracker.start_download(
            download_id,
            filename,
            site_name or "Unknown",
            media_type,
            path=os.path.abspath(path),
        )
        download_tracker.update_status(download_id, "downloading")

    # Set headers
    headers = {}
    if referer:
        headers["Referer"] = referer

    if headers_:
        headers.update(headers_)
    else:
        headers["User-Agent"] = get_userAgent()

    # Set interrupt handler (only in main thread)
    temp_path = f"{path}.temp"
    interrupt_handler = InterruptHandler()

    try:
        if threading.current_thread() is threading.main_thread():
            previous_handler = signal.getsignal(signal.SIGINT)
            signal.signal(
                signal.SIGINT,
                partial(
                    signal_handler,
                    interrupt_handler=interrupt_handler,
                    original_handler=previous_handler,
                ),
            )

    except Exception:
        logger.exception("threading failed")

    # Ensure the output directory exists
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with create_client() as client:
        try:
            head = client.head(url, headers=headers)
            head.raise_for_status()
            content_type = (head.headers.get("content-type") or "").lower()
        except httpx2.HTTPError:
            content_type = ""

        # If HEAD indicates HTML/JSON, attempt a GET without Range/If-Range as fallback
        if "text/html" in content_type or "application/json" in content_type:
            console.print(
                "[yellow]HEAD indicates non-video; retrying GET without Range/If-Range..."
            )

            try:
                resp_check = client.get(url, headers=headers)
                resp_check.raise_for_status()
                preview_text = None

                try:
                    preview = resp_check.content[:2000]
                    preview_text = preview.decode("utf-8", errors="replace")
                except httpx2.HTTPError:
                    preview_text = "<could not read body>"
                    return None, False

                console.print("\n[red]--- body preview ---")
                console.print(preview_text)
                return None, False

            except httpx2.HTTPError as e:
                console.print(f"[red]Fallback GET failed: {e}")
                return None, False

        # Open the streaming response using the effective headers
        with client.stream("GET", url, headers=headers) as response:
            response.raise_for_status()

            # Respect content-length when provided; otherwise treat as unknown (streaming/chunked)
            content_length = response.headers.get("content-length")
            try:
                total = int(content_length) if content_length is not None else None
            except (ValueError, TypeError):
                total = None

            if total is None:
                console.print(
                    "[yellow]No Content-Length received; streaming until peer closes connection."
                )

            start_time = time.time()
            downloaded = 0
            incomplete_error = False
            speed_samples = deque()

            # Unified progress bar manager (Rich in CLI, null-context in GUI)
            with DownloadBarManager(download_id) as bar_mgr:
                bar_mgr.add_prebuilt_tasks([("video", "MP4")])

                with open(temp_path, "wb") as file:
                    try:
                        for chunk in response.iter_bytes(chunk_size=65536):
                            if interrupt_handler.force_quit or (
                                download_id and download_tracker.is_stopped(download_id)
                            ):
                                console.print(
                                    "\n[red]Force quitting... Saving partial download."
                                )
                                if download_id and download_tracker.is_stopped(
                                    download_id
                                ):
                                    incomplete_error = "cancelled"
                                break

                            if chunk:
                                size = file.write(chunk)
                                downloaded += size

                                # Calculate stats
                                elapsed = time.time() - start_time

                                # Windowed speed calculation (3s sliding window)
                                now = time.time()
                                speed_samples.append((now, downloaded))
                                while speed_samples and now - speed_samples[0][0] > 3.0:
                                    speed_samples.popleft()
                                if len(speed_samples) >= 2:
                                    bytes_delta = downloaded - speed_samples[0][1]
                                    time_delta = now - speed_samples[0][0]
                                    speed = (
                                        bytes_delta / time_delta if time_delta > 0 else 0
                                    )
                                else:
                                    speed = downloaded / elapsed if elapsed > 0 else 0
                                speed_str = (
                                    internet_manager.format_transfer_speed(speed)
                                    if elapsed > 0
                                    else "-- B/s"
                                )

                                if total:
                                    remaining_bytes = max(total - downloaded, 0)
                                    eta_seconds = (
                                        remaining_bytes / speed
                                        if (elapsed > 0 and speed > 0)
                                        else 0
                                    )
                                    eta_str = internet_manager.format_time(eta_seconds)
                                else:
                                    eta_str = "--"

                                # Format downloaded size
                                downloaded_value, downloaded_unit = (
                                    internet_manager.format_file_size(downloaded).split(
                                        " "
                                    )
                                )

                                percent = (downloaded / total * 100) if total else 0
                                total_size_str = (
                                    f"{(total / 1024 / 1024):.2f}MB"
                                    if total
                                    else "Unknown"
                                )

                                bar_mgr.handle_progress_line(
                                    {
                                        "task_key": "video",
                                        "label": "MP4",
                                        "pct": percent,
                                        "speed": speed_str,
                                        "size": f"{downloaded_value} {downloaded_unit}/{total_size_str if total else '??'}",
                                        "duration": eta_str,
                                    }
                                )

                    except KeyboardInterrupt:
                        if not interrupt_handler.force_quit:
                            interrupt_handler.kill_download = True

                    except (httpx2.HTTPError, OSError) as e:
                        incomplete_error = True
                        interrupt_handler.kill_download = True
                        console.print(
                            f"\n[red]Download error: {e}. Saving partial download."
                        )

                    finally:
                        try:
                            file.flush()
                            os.fsync(file.fileno())
                        except OSError as e:
                            logger.error(f"error:{e}")

    if os.path.exists(temp_path):
        if incomplete_error == "cancelled":
            if download_id:
                download_tracker.complete_download(
                    download_id, success=False, error="cancelled"
                )
            return None, True

        last_exc = None
        for attempt in range(10):
            try:
                os.replace(temp_path, path)
                last_exc = None
                break

            except PermissionError as e:
                last_exc = e
                console.log(f"[yellow]Rename attempt {attempt + 1}/10 failed: {e}")
                time.sleep(0.5)
                import gc

                gc.collect()

        if last_exc:
            console.print(f"[red]Could not rename temp file after retries: {last_exc}")
            return None, interrupt_handler.kill_download

    if os.path.exists(path):
        if show_final_info:
            file_size = internet_manager.format_file_size(os.path.getsize(path))
            console.print("\n[green]Output:")
            console.print(f"  [cyan]Path: [red]{os.path.abspath(path)}")
            console.print(f"  [cyan]Size: [red]{file_size}")

            if incomplete_error or (total and os.path.getsize(path) < total):
                console.print(
                    "[yellow]Warning: download was incomplete (partial file saved)."
                )

        if CREATE_NFO_FILES:
            create_nfo(path)

        if KODI_NFO_FILES:
            generate_kodi_metadata(path, media_type=context_tracker.media_type)

        if download_id:
            abs_path = os.path.abspath(path)
            download_tracker.complete_download(download_id, success=True, path=abs_path)

        return path, interrupt_handler.kill_download

    else:
        console.print("[red]Download failed or file is empty.")
        if download_id:
            download_tracker.complete_download(
                download_id, success=False, error="File missing or empty"
            )
        return None, interrupt_handler.kill_download
