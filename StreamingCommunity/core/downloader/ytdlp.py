# 26.11.26 - yt-dlp download engine for HLS and progressive (MP4) streams

from __future__ import annotations

import logging
import os
import re
from typing import Any, Callable

import yt_dlp
from yt_dlp.utils import DownloadCancelled, DownloadError

# Internal utilities
from StreamingCommunity.core.ui.bar_manager import DownloadBarManager
from StreamingCommunity.source.utils.tracker import context_tracker, download_tracker
from StreamingCommunity.utils import config_manager, internet_manager, os_manager
from StreamingCommunity.utils.console.shared import console
from StreamingCommunity.utils.http_client import get_headers

# Config
EXTENSION_OUTPUT = config_manager.config.get("PROCESS", "extension")
SKIP_DOWNLOAD = config_manager.config.get_bool("DOWNLOAD", "skip_download")
REFRESH_RETRIES = config_manager.config.get_int(
    "DOWNLOAD", "hls_refresh_retry", default=3
)
DEFAULT_FORMAT = "bv*+ba/b"
logger = logging.getLogger(__name__)


def _cfg(section: str, key: str, default: Any = None) -> Any:
    try:
        return config_manager.config.get(section, key, default=default)
    except (ValueError, KeyError):
        return default


def _cfg_int(section: str, key: str, default: int = 0) -> int:
    try:
        return config_manager.config.get_int(section, key, default=default)
    except (ValueError, KeyError):
        return default


def _cfg_bool(section: str, key: str, default: bool = False) -> bool:
    try:
        return config_manager.config.get_bool(section, key, default=default)
    except (ValueError, KeyError):
        return default


def _audio_selector() -> str:
    """Translate the N_m3u8DL-RE ``select_audio`` language hint to yt-dlp.

    ``lang='ita|Ita|it':for=best`` becomes a yt-dlp audio selector that prefers
    those language codes and falls back to the best audio track.
    """
    select_audio = str(_cfg("DOWNLOAD", "select_audio", "") or "").strip()
    match = re.search(r"lang='([^']+)'", select_audio)
    if not match:
        return "ba"

    langs = [item.strip() for item in match.group(1).split("|") if item.strip()]
    if not langs:
        return "ba"

    pattern = "|".join(re.escape(item) for item in langs)
    return f"ba[language~='(?i)^({pattern})$']"


def _resolve_format(audio_only: bool = False) -> str:
    """Build the yt-dlp format selector from the existing download config."""
    if audio_only:
        return "ba/b"

    custom = str(_cfg("DOWNLOAD", "ytdlp_format", "") or "").strip()
    if custom:
        return custom

    audio = _audio_selector()
    select_video = str(_cfg("DOWNLOAD", "select_video", "best") or "best").strip()

    if select_video.isdigit():
        height = int(select_video)
        if audio == "ba":
            return f"bv*[height<={height}]+ba/b[height<={height}]"
        return (
            f"bv*[height<={height}]+{audio}/"
            f"bv*[height<={height}]+ba/b[height<={height}]"
        )

    # A raw yt-dlp selector is accepted as-is.
    if select_video != "best" and any(char in select_video for char in "[+/"):
        return select_video

    if audio == "ba":
        return "bv*+ba/b"
    return f"bv*+{audio}/bv*+ba/b"


def _proxy() -> str | None:
    if not _cfg_bool("REQUESTS", "use_proxy", False):
        return None
    try:
        proxies = config_manager.config.get_dict("REQUESTS", "proxy") or {}
    except (ValueError, KeyError):
        return None
    if not isinstance(proxies, dict):
        return None
    return proxies.get("https") or proxies.get("http") or None


def _ffmpeg_path() -> str | None:
    try:
        from StreamingCommunity.setup import get_ffmpeg_path

        return get_ffmpeg_path()
    except Exception:
        return None


class YTDLP_Downloader:
    """Download an HLS playlist or a progressive URL with yt-dlp.

    The public interface mirrors :class:`HLS_Downloader`: ``start()`` returns
    ``(path, kill_handler)``. ``playlist_resolver`` is used to mint a fresh
    signed playlist URL when the current one expires mid-download.
    """

    def __init__(
        self,
        url: str,
        output_path: str | None = None,
        headers: dict[str, str] | None = None,
        audio_only: bool = False,
        playlist_resolver: Callable[[], str | None] | None = None,
        download_id: str | None = None,
        site_name: str | None = None,
    ):
        self.url = str(url).strip()
        self.playlist_resolver = playlist_resolver
        self.custom_headers = headers if headers is not None else get_headers()
        self.audio_only = audio_only

        if not output_path:
            output_path = f"download.{EXTENSION_OUTPUT}"

        self.output_path = os_manager.get_sanitize_path(output_path)
        if not os.path.splitext(self.output_path)[1]:
            self.output_path += f".{EXTENSION_OUTPUT}"

        self.output_ext = (
            os.path.splitext(self.output_path)[1].lstrip(".").lower()
            or EXTENSION_OUTPUT
        )

        # Tracking IDs - fall back to the current context like the other engines.
        self.download_id = download_id or context_tracker.download_id
        self.site_name = site_name or context_tracker.site_name

        self.file_already_exists = os.path.exists(self.output_path)
        self.error: str | None = None

    def start(self) -> tuple[str | None, bool]:
        """Run the download and return ``(output_path, cancelled)``."""
        if self.file_already_exists:
            console.print("[yellow]File already exists.")
            return self.output_path, False

        if SKIP_DOWNLOAD:
            console.print("[yellow]Skipping download as per configuration.")
            return self.output_path, False

        os.makedirs(os.path.dirname(self.output_path) or ".", exist_ok=True)

        if self.download_id:
            download_tracker.update_status(self.download_id, "downloading")

        console.print("[dim]Starting yt-dlp download ...")

        attempts = 0
        while True:
            attempts += 1
            try:
                self._download_once()
                break

            except DownloadCancelled:
                console.print("[yellow]Download cancelled.")
                self._complete(False, "cancelled")
                return None, True

            except KeyboardInterrupt:
                console.print("[yellow]Download interrupted.")
                self._complete(False, "cancelled")
                return None, True

            except DownloadError as exc:
                reason = str(exc) or exc.__class__.__name__
                if self.playlist_resolver is not None and attempts <= REFRESH_RETRIES:
                    fresh = self._resolve_fresh_playlist()
                    if fresh and fresh != self.url:
                        console.print(
                            f"[yellow]Download failed ({reason}). Refreshing the "
                            f"playlist URL and retrying "
                            f"({attempts}/{REFRESH_RETRIES})..."
                        )
                        self.url = fresh
                        continue

                self.error = reason
                console.print(f"[red]Download failed: {reason}")
                self._complete(False, reason)
                return None, False

            except Exception as exc:
                self.error = str(exc)
                logger.exception("yt-dlp download failed")
                console.print(f"[red]Download failed: {exc}")
                self._complete(False, str(exc))
                return None, False

        final_path = self._find_output()
        if not final_path:
            reason = "Downloaded file not found"
            console.print(f"[red]{reason}")
            self._complete(False, reason)
            return None, False

        self._print_summary(final_path)
        self._complete(True, None, final_path)
        return final_path, False

    def _download_once(self) -> None:
        with DownloadBarManager(self.download_id) as bar_mgr:
            bar_mgr.add_prebuilt_tasks([("video", "Video")])
            with yt_dlp.YoutubeDL(self._build_options(bar_mgr)) as ydl:  # type: ignore[arg-type]
                ydl.download([self.url])  # type: ignore[arg-type]

    def _build_options(self, bar_mgr: DownloadBarManager) -> dict[str, Any]:
        stem = os.path.splitext(self.output_path)[0].replace("%", "%%")
        headers = {
            key: value
            for key, value in (self.custom_headers or {}).items()
            if value
        }

        options: dict[str, Any] = {
            "format": _resolve_format(self.audio_only),
            "outtmpl": f"{stem}.%(ext)s",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "retries": max(1, _cfg_int("DOWNLOAD", "retry_count", 30)),
            "fragment_retries": max(1, _cfg_int("DOWNLOAD", "retry_count", 30)),
            "concurrent_fragment_downloads": max(
                1, _cfg_int("DOWNLOAD", "thread_count", 8)
            ),
            "http_headers": headers,
            "progress_hooks": [lambda data: self._progress_hook(bar_mgr, data)],
            "socket_timeout": max(1, _cfg_int("REQUESTS", "timeout", 30)),
        }

        if headers:
            user_agent = headers.get("User-Agent") or headers.get("user-agent")
            if user_agent:
                options["user_agent"] = user_agent

        if not self.audio_only:
            # Force the requested container even for single-format HLS streams.
            options["merge_output_format"] = self.output_ext
            options["remux_video"] = self.output_ext

        proxy = _proxy()
        if proxy:
            options["proxy"] = proxy

        if not _cfg_bool("REQUESTS", "verify", True):
            options["nocheckcertificate"] = True

        ffmpeg_path = _ffmpeg_path()
        if ffmpeg_path:
            options["ffmpeg_location"] = ffmpeg_path

        return options

    def _progress_hook(self, bar_mgr: DownloadBarManager, data: dict[str, Any]) -> None:
        if self.download_id and download_tracker.is_stopped(self.download_id):
            raise DownloadCancelled("cancelled by user")

        status = data.get("status")
        if status == "downloading":
            downloaded = data.get("downloaded_bytes") or 0
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            speed = data.get("speed") or 0.0
            eta = data.get("eta")

            percent = (downloaded / total * 100.0) if total else 0.0
            size = (
                f"{internet_manager.format_file_size(downloaded)}/"
                f"{internet_manager.format_file_size(total) if total else '??'}"
            )
            speed_text = (
                internet_manager.format_transfer_speed(float(speed))
                if speed
                else "0B/s"
            )
            duration = (
                internet_manager.format_time(eta) if eta is not None else "--"
            )

            payload: dict[str, Any] = {
                "task_key": "video",
                "label": "Video",
                "pct": percent,
                "speed": speed_text,
                "size": size,
                "duration": duration,
            }

            fragment_index = data.get("fragment_index")
            fragment_count = data.get("fragment_count")
            if fragment_index is not None and fragment_count:
                payload["segments"] = f"{fragment_index}/{fragment_count}"

            bar_mgr.handle_progress_line(payload)

        elif status == "finished":
            bar_mgr.handle_progress_line(
                {
                    "task_key": "video",
                    "label": "Video",
                    "pct": 100,
                    "speed": "0B/s",
                    "size": "",
                    "duration": "00:00",
                }
            )

    def _resolve_fresh_playlist(self) -> str | None:
        if self.playlist_resolver is None:
            return None
        try:
            fresh = self.playlist_resolver()
        except Exception as exc:
            logger.error("Playlist refresh failed: %s", exc)
            return None
        return str(fresh).strip() if fresh else None

    def _find_output(self) -> str | None:
        """Locate the produced file, tolerating yt-dlp extension choices."""
        if os.path.exists(self.output_path):
            return self.output_path

        directory = os.path.dirname(self.output_path) or "."
        stem = os.path.basename(os.path.splitext(self.output_path)[0])

        try:
            names = os.listdir(directory)
        except OSError:
            return None

        candidates: list[str] = []
        for name in names:
            if not (name == stem or name.startswith(f"{stem}.")):
                continue
            if os.path.splitext(name)[1].lower() in (".part", ".ytdl", ".temp"):
                continue
            candidates.append(os.path.join(directory, name))

        if not candidates:
            return None

        preferred = [
            candidate
            for candidate in candidates
            if os.path.splitext(candidate)[1].lstrip(".").lower() == self.output_ext
        ]

        if preferred:
            best = max(preferred, key=os.path.getsize)
            if os.path.abspath(best) != os.path.abspath(self.output_path):
                try:
                    os.replace(best, self.output_path)
                    return self.output_path
                except OSError:
                    return best
            return best

        # The container differs from the requested one (e.g. remux was skipped).
        # Return the real file instead of renaming it to a wrong extension.
        return max(candidates, key=os.path.getsize)

    def _complete(
        self,
        success: bool,
        error: str | None = None,
        path: str | None = None,
    ) -> None:
        if self.download_id:
            download_tracker.complete_download(
                self.download_id,
                success=success,
                error=error,
                path=os.path.abspath(path) if path else None,
            )

    def _print_summary(self, path: str) -> None:
        if not os.path.exists(path):
            return

        file_size = internet_manager.format_file_size(os.path.getsize(path))
        console.print("\n[green]Output:")
        console.print(f"  [cyan]Path: [red]{os.path.abspath(path)}")
        console.print(f"  [cyan]Size: [red]{file_size}")
