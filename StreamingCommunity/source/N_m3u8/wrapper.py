# 04.01.25

from logging import raiseExceptions
import json
import queue
import re
import asyncio
import platform
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.parse import parse_qs, urlparse


# External
from rich.console import Console

# Internal
from StreamingCommunity.utils.config import config_manager
from StreamingCommunity.utils.console.shared import SCHEMA_THEME
from StreamingCommunity.utils.os import internet_manager
from StreamingCommunity.core.ui.bar_manager import DownloadBarManager
from StreamingCommunity.setup import (
    get_ffmpeg_path,
    get_n_m3u8dl_re_path,
    get_bento4_decrypt_path,
    get_shaka_packager_path,
)
from StreamingCommunity.source.utils.tracker import download_tracker
from StreamingCommunity.utils.http_client import create_async_client
from StreamingCommunity.source.utils.trans_codec import get_subtitle_codec_name
from StreamingCommunity.source.Manual.decrypt.decrypt import Decryptor
from StreamingCommunity.torrent.title_parser import TorrentResult


# Logic
from ..utils.object import StreamInfo, KeysManager
from .pattern import (
    VIDEO_LINE_RE,
    AUDIO_LINE_RE,
    SUBTITLE_LINE_RE,
    SEGMENT_RE,
    PERCENT_RE,
    SPEED_RE,
    SIZE_RE,
    SUBTITLE_FINAL_SIZE_RE,
)
from .parser import parse_meta_json, LogParser
from .ui import build_table


# Variable
console = Console(
    theme=SCHEMA_THEME,
    force_terminal=True if platform.system().lower() != "windows" else None,
)


def _cfg(section, key, default=None):
    return (
        config_manager.config.get(section, key, default=default)
        if default is not None
        else config_manager.config.get(section, key)
    )


def _cfg_bool(section, key, default=False):
    return config_manager.config.get_bool(section, key, default=default)


def _cfg_int(section, key, default=0):
    return config_manager.config.get_int(section, key, default=default)


def _cfg_dict(section, key, default=None):
    return config_manager.config.get_dict(
        section, key, default=default if default is not None else {}
    )


_PROGRESS_PREFIX_RE = re.compile(r"(Vid|Aud|Sub)\s")
_AUTH_ERROR_RE = re.compile(r"\b(?:401|403)\b|forbidden|unauthorized", re.IGNORECASE)
_SEGMENT_FILE_EXTS = {".ts", ".m4s", ".mp4", ".aac", ".m4a"}
_QUEUE_END = object()
_QUEUE_EMPTY = object()
# Give in-flight segments a few seconds after the signed URL expiry before
# aborting and asking the site for a fresh playlist URL.
_URL_EXPIRY_GRACE = 10.0


def _read_download_output(stream):
    """Yield ``(text, is_log)`` fragments from N_m3u8DL-RE's stdout.

    N_m3u8DL-RE refreshes its progress bar in place (``\\r`` updates, or
    plain concatenation when stdout is a pipe), so a ``for line in
    proc.stdout`` loop (which only splits on ``\\n``) buffers every progress
    update until the process ends and the Rich bar never updates. We split on
    ``\\n`` for log lines AND on the ``Vid``/``Aud``/``Sub`` prefixes that
    begin each progress update.
    """
    buf = ""
    prefix_re = re.compile(r"(Vid|Aud|Sub)\s")
    while True:
        chunk = stream.read(1024)
        if not chunk:
            break
        buf += chunk

        boundaries = [(m.start(), "p") for m in prefix_re.finditer(buf)]
        pos = 0
        while True:
            nl = buf.find("\n", pos)
            if nl == -1:
                break
            boundaries.append((nl, "l"))
            pos = nl + 1
        boundaries.sort()

        start = 0
        for bpos, bkind in boundaries:
            if bpos == start and bkind == "p":
                continue
            token = buf[start:bpos]
            if bkind == "l":
                start = bpos + 1
                if token:
                    yield token, "log"
            else:
                start = bpos
                if token:
                    yield token, "progress"
        buf = buf[start:]
    if buf:
        yield buf, "log"


class MediaDownloader:
    def __init__(
        self,
        url: Optional[str],
        output_dir: Optional[str],
        filename: Optional[str],
        headers: Optional[Dict] = None,
        key: Optional[str] = None,
        cookies: Optional[Dict] = None,
        decrypt_preference: Optional[str] = "shaka",
        download_id: Optional[str] = None,
        site_name: Optional[str] = None,
        audio_only: bool = False,
    ):
        self.url = url
        self.output_dir = Path(output_dir)
        self.filename = filename
        self.headers = headers or {}
        self.key = key
        self.cookies = cookies or {}
        self.decrypt_preference = str(decrypt_preference).strip().lower()
        self.download_id = download_id
        self.site_name = site_name
        self.streams = []
        self.external_subtitles = []
        self.force_best_video = False
        self.audio_only = audio_only
        (
            self.meta_json_path,
            self.meta_selected_path,
            self.raw_m3u8,
            self.raw_mpd,
            self.raw_ism,
        ) = None, None, None, None, None
        self.status = None
        self.manifest_type = "Unknown"
        self.parse_exit_code = None
        self.parse_error = None
        self.exit_code = None
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir_type = (
            "Movie"
            if config_manager.config.get("OUTPUT", "movie_folder_name")
            in str(self.output_dir)
            else "TV"
            if config_manager.config.get("OUTPUT", "serie_folder_name")
            in str(self.output_dir)
            else "Anime"
            if config_manager.config.get("OUTPUT", "anime_folder_name")
            in str(self.output_dir)
            else "other"
        )

        # Track in GUI if ID is provided
        if self.download_id:
            download_tracker.start_download(
                self.download_id,
                self.filename,
                self.site_name or "Unknown",
                self.output_dir_type,
            )

    def _normalize_filter(self, filter_value: str) -> str:
        """Normalize filter ensuring values are quoted if they contain special characters"""
        if not filter_value:
            return filter_value

        parts, normalized_parts, special_chars = (
            filter_value.split(":"),
            [],
            "|=.*+?[]{}()^$",
        )
        for part in parts:
            if "=" in part:
                key, val = part.split("=", 1)
                val = val.strip("'\"")
                normalized_parts.append(
                    f'{key}="{val}"'
                    if any(c in val for c in special_chars)
                    else f"{key}={val}"
                )
            else:
                normalized_parts.append(part)

        return ":".join(normalized_parts)

    def _get_common_args(self) -> List[str]:
        """Get common command line arguments for N_m3u8DL-RE"""
        cmd = []
        if self.headers:
            cmd.extend(
                [
                    item
                    for k, v in self.headers.items()
                    for item in ["--header", f"{k}: {v}"]
                ]
            )

        if self.cookies and (
            cookie_str := "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        ):
            cmd.extend(["--header", f"Cookie: {cookie_str}"])

        if _cfg_bool("REQUESTS", "use_proxy"):
            proxy_cfg = _cfg_dict("REQUESTS", "proxy")
            proxy_url = proxy_cfg.get("https") or proxy_cfg.get("http")
            if proxy_url:
                cmd.extend(["--use-system-proxy", "false", "--custom-proxy", proxy_url])

        cmd.extend(["--force-ansi-console", "--no-ansi-color"])
        return cmd

    def determine_decryption_tool(self) -> str | None:
        """Determine decryption tool based on preference and availability"""
        if self.decrypt_preference == "bento4":
            return get_bento4_decrypt_path()
        if self.decrypt_preference == "shaka":
            return get_shaka_packager_path()
        return get_shaka_packager_path()

    def _match_external_subtitle_lang(self, ext_lang: str) -> bool:
        """Check if external subtitle language matches filter"""
        sub_filter = _cfg("DOWNLOAD", "select_subtitle")
        if not ext_lang or not sub_filter:
            return False

        try:
            if lang_match := re.search(r"lang=['\"]([^'\"]+)['\"]", sub_filter):
                return any(
                    t.lower() == ext_lang.lower()
                    or ext_lang.lower().startswith(t.lower())
                    or t.lower() in ext_lang.lower()
                    for t in [
                        x.strip() for x in lang_match.group(1).split("|") if x.strip()
                    ]
                )
            return any(
                t.lower() in ext_lang.lower()
                for t in re.findall(r"[A-Za-z]{2,}", sub_filter)
            )
        except Exception:
            return False

    def parser_stream(self) -> List[StreamInfo]:
        """Analyze playlist and display table of available streams"""
        self.parse_error = None
        self.parse_exit_code = None
        analysis_path = self.output_dir / "analysis_temp"
        analysis_path.mkdir(exist_ok=True)
        # Drop metadata from a previous (possibly failed) analysis so a failed
        # re-parse cannot be mistaken for a successful one.
        for stale in (
            analysis_path / "temp_analysis" / "meta.json",
            analysis_path / "temp_analysis" / "meta_selected.json",
        ):
            try:
                stale.unlink()
            except FileNotFoundError:
                pass
        if self.download_id:
            download_tracker.update_status(self.download_id, "Parsing...")

        # Normalize filter values
        filters = getattr(self, "custom_filters", None)
        norm_v = self._normalize_filter(
            filters["video"]
            if filters and filters.get("video")
            else _cfg("DOWNLOAD", "select_video")
        )
        norm_a = self._normalize_filter(
            filters["audio"]
            if filters and filters.get("audio")
            else _cfg("DOWNLOAD", "select_audio")
        )
        norm_s = self._normalize_filter(
            filters["subtitle"]
            if filters and filters.get("subtitle")
            else _cfg("DOWNLOAD", "select_subtitle")
        )

        cmd = [
            get_n_m3u8dl_re_path(),
            "--write-meta-json",
            "--no-log",
            "--save-dir",
            str(analysis_path),
            "--tmp-dir",
            str(analysis_path),
            "--save-name",
            TorrentResult.safe_arg("temp_analysis"),
            "--select-video",
            TorrentResult.safe_arg(norm_v),
            "--select-audio",
            TorrentResult.safe_arg(norm_a),
            "--select-subtitle",
            TorrentResult.safe_arg(norm_s),
            "--skip-download",
        ]
        cmd.extend(self._get_common_args())
        cmd.append(TorrentResult.safe_arg(self.url))
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            universal_newlines=True,
        )

        # Save parsing log
        log_parser = LogParser()
        log_path = self.output_dir / f"{self.filename}_parsing.log"
        with open(log_path, "w", encoding="utf-8", errors="replace") as log_file:
            log_file.write(f"Command: {' '.join(cmd)}\n{'=' * 80}\n\n")
            for line in proc.stdout:
                if line := line.rstrip():
                    log_parser.parse_line(line)
                    log_file.write(line + "\n")
                    log_file.flush()
            proc.wait()

        self.parse_exit_code = proc.returncode
        analysis_dir = analysis_path / "temp_analysis"
        self.meta_json_path = analysis_dir / "meta.json"
        self.meta_selected_path = analysis_dir / "meta_selected.json"
        self.raw_m3u8 = analysis_dir / "raw.m3u8"
        self.raw_mpd = analysis_dir / "raw.mpd"
        self.raw_ism = analysis_dir / "raw.ism"

        # Determine manifest type
        self.manifest_type = (
            "DASH"
            if self.raw_mpd.exists()
            else "HLS"
            if self.raw_m3u8.exists()
            else "ISM"
            if self.raw_ism.exists()
            else "Unknown"
        )

        if self.meta_json_path.exists():
            self.streams = parse_meta_json(
                str(self.meta_json_path), str(self.meta_selected_path)
            )

            # Check if video needs to be forced (skip for audio-only downloads)
            if not self.audio_only:
                try:
                    has_video = any(s.type == "Video" for s in self.streams)
                    video_selected = any(
                        s.type == "Video" and s.selected for s in self.streams
                    )
                    if has_video and not video_selected:
                        console.print(
                            "[yellow]No video matched select_video filter; forcing 'best' for download[/yellow]"
                        )
                        self.force_best_video = True
                except Exception:
                    self.force_best_video = False

            # Add external subtitles to stream list
            for ext_sub in self.external_subtitles:
                ext_lang = ext_sub.get("language", "") or ""
                selected = self._match_external_subtitle_lang(ext_lang)
                ext_type = ext_sub.get("type") or ext_sub.get("format") or "srt"
                ext_sub["_selected"] = selected
                ext_sub["_ext"] = ext_type
                self.streams.append(
                    StreamInfo(
                        type="Subtitle [red]*EXT",
                        language=ext_sub.get("language", ""),
                        name=ext_sub.get("name", ""),
                        selected=selected,
                        extension=ext_type,
                    )
                )

            # Show table
            selected_set = {
                i for i, s in enumerate(self.streams) if getattr(s, "selected", False)
            }
            console.print(
                build_table(
                    self.streams,
                    selected_set,
                    0,
                    window_size=len(self.streams),
                    highlight_cursor=False,
                )
            )
            return self.streams

        if proc.returncode not in (0, None):
            self.parse_error = self._format_failure(proc.returncode, log_parser.errors)
            console.print(f"[red]{self.parse_error}")

        return []

    @staticmethod
    def _format_failure(returncode, errors, max_lines: int = 3) -> str:
        """Build a readable failure message from the downloader's error lines."""
        tail = [str(e).strip() for e in errors[-max_lines:] if str(e).strip()]
        detail = " | ".join(tail) if tail else "no error output"
        return f"N_m3u8DL-RE exited with code {returncode}: {detail}"

    @staticmethod
    def _looks_like_expired_token(errors) -> bool:
        """Heuristics for a signed-URL/token rejection (worth refreshing the URL)."""
        joined = " ".join(str(e) for e in errors[-20:]).lower()
        markers = ("403", "forbidden", "unauthorized", "401", "expired", "token")
        return any(marker in joined for marker in markers)

    def get_metadata(self) -> tuple:
        """Get paths to metadata files"""
        return (
            str(self.meta_json_path),
            str(self.meta_selected_path),
            str(self.raw_m3u8),
            str(self.raw_mpd),
            str(self.raw_ism),
        )

    def set_key(self, key):
        """Set decryption key"""
        if isinstance(key, KeysManager):
            self.key = key.get_keys_list()
        else:
            self.key = key

    async def _download_external_subtitles(self):
        """Download external subtitles using httpx2"""
        if not self.external_subtitles:
            return []

        downloaded = []
        async with create_async_client(headers=self.headers) as client:
            for idx, sub in enumerate(self.external_subtitles):
                try:
                    if not sub.get("_selected", True):
                        continue

                    url, lang = sub["url"], sub.get("language", "unknown")
                    sub_type = (
                        sub.get("_ext") or sub.get("type") or sub.get("format") or "srt"
                    )
                    original_type = sub.get("type")

                    # Handle 'captions' type getting mapped to wrong extension
                    if sub_type == "captions":
                        sub_type = "vtt"

                    # Determine filename suffix
                    fname_suffix = lang
                    if (
                        original_type == "captions"
                        or original_type == "closed_captions"
                    ):
                        fname_suffix = f"{lang}_captions"

                    sub_path = (
                        self.output_dir / f"{self.filename}.{fname_suffix}.{sub_type}"
                    )
                    response = await client.get(url)
                    response.raise_for_status()

                    with open(sub_path, "wb") as f:
                        f.write(response.content)
                    downloaded.append(
                        {
                            "path": str(sub_path),
                            "language": lang,
                            "type": sub_type,
                            "size": len(response.content),
                        }
                    )

                    # Update download progress for external subtitle
                    if self.download_id and download_tracker:
                        track_key = f"subtitle_{fname_suffix}"
                        download_tracker.update_status(self.download_id, "downloading")
                        download_tracker.update_progress(
                            self.download_id,
                            track_key,
                            progress=100.0,
                            size=f"{len(response.content) / 1024:.2f}KB",
                            speed="N/A",  # Too fast/small to calculate meaningful speed
                            segments="1/1",
                            status="completed",
                        )

                except Exception as e:
                    console.log(f"[red]Failed to download external subtitle: {e}[/red]")
                    if self.download_id and download_tracker:
                        download_tracker.update_progress(
                            self.download_id, f"subtitle_{lang}_{idx}", status="failed"
                        )
        return downloaded

    def start_download(
        self,
        resume_from: Optional[int] = None,
        resume_tmp: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Start the download process.

        When ``resume_from`` is set, only the remaining segments are fetched
        (``--custom-range``) and kept on disk (``--skip-merge``) so the caller
        can concatenate them with the already-downloaded prefix.
        """
        is_resume = resume_from is not None
        # A short, fixed save name keeps resume paths below Windows limits; the
        # caller already gives every resume attempt its own directory.
        save_name = "resume" if is_resume else self.filename
        if is_resume:
            save_dir = Path(resume_tmp or self.output_dir)
            tmp_dir = save_dir
            save_dir.mkdir(parents=True, exist_ok=True)
        else:
            save_dir = self.output_dir
            tmp_dir = self.output_dir

        filters = getattr(self, "custom_filters", None)

        # Determine filters
        norm_v = self._normalize_filter(
            filters["video"]
            if filters and "video" in filters
            else (
                "best"
                if getattr(self, "force_best_video", False)
                else _cfg("DOWNLOAD", "select_video")
            )
        )
        norm_a = self._normalize_filter(
            filters["audio"]
            if filters and "audio" in filters
            else _cfg("DOWNLOAD", "select_audio")
        )
        norm_s = self._normalize_filter(
            filters["subtitle"]
            if filters and "subtitle" in filters
            else _cfg("DOWNLOAD", "select_subtitle")
        )

        # Build command
        cmd = [
            get_n_m3u8dl_re_path(),
            "--save-name",
            TorrentResult.safe_arg(save_name),
            "--save-dir",
            str(save_dir),
            "--tmp-dir",
            str(tmp_dir),
            "--ffmpeg-binary-path",
            get_ffmpeg_path(),
            "--decryption-binary-path",
            self.determine_decryption_tool(),
            "--no-log",
            "--write-meta-json",
            "false",
            "--binary-merge",
            "--del-after-done",
            "false" if is_resume else "true",
            "--auto-subtitle-fix",
            "false",
            "--check-segments-count",
            (
                "false"
                if is_resume
                else "true"
                if _cfg_bool("DOWNLOAD", "check_segments_count")
                else "false"
            ),
            "--mp4-real-time-decryption",
            "true" if _cfg_bool("DOWNLOAD", "real_time_decryption") else "false",
        ]

        if is_resume:
            # Keep the segments: the caller merges them with the prefix.
            cmd.extend(
                [
                    "--custom-range",
                    f"{int(resume_from)}-",
                    "--skip-merge",
                ]
            )

        if self.audio_only:
            # Drop all video streams — download audio only
            cmd.extend(["--drop-video", "all"])
        else:
            cmd.extend(["--select-video", TorrentResult.safe_arg(norm_v)])

        if norm_a:
            cmd.extend(["--select-audio", TorrentResult.safe_arg(norm_a)])

        if not self.audio_only:
            sub_filter_val = _cfg("DOWNLOAD", "select_subtitle")
            if sub_filter_val == "false":
                cmd.extend(["--drop-subtitle", "all"])
            elif norm_s:
                cmd.extend(["--select-subtitle", TorrentResult.safe_arg(norm_s)])
        cmd.extend(self._get_common_args())

        # Add optional parameters
        if _cfg_bool("DOWNLOAD", "concurrent_download"):
            cmd.append("--concurrent-download")
        thread_count_val = _cfg_int("DOWNLOAD", "thread_count")
        if thread_count_val > 0:
            cmd.extend(["--thread-count", str(thread_count_val)])
        req_timeout_val = _cfg_int("REQUESTS", "timeout")
        if req_timeout_val > 0:
            cmd.extend(["--http-request-timeout", str(req_timeout_val)])
        retry_val = _cfg_int("DOWNLOAD", "retry_count")
        if retry_val > 0:
            cmd.extend(["--download-retry-count", str(retry_val)])
        max_speed_val = _cfg("DOWNLOAD", "max_speed")
        if max_speed_val and str(max_speed_val).lower() != "false":
            cmd.extend(["--max-speed", max_speed_val])
        if self.key:
            keys_list = (
                self.key.get_keys_list()
                if isinstance(self.key, KeysManager)
                else ([self.key] if isinstance(self.key, str) else self.key)
            )
            for single_key in keys_list:
                cmd.extend(["--key", single_key])

        cmd.append(TorrentResult.safe_arg(self.url))

        # External subtitles only need to be fetched once, not on every resume.
        external_subs = []
        if not is_resume:
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                external_subs = loop.run_until_complete(
                    self._download_external_subtitles()
                )
            finally:
                loop.close()

        log_parser = LogParser(show_warnings=False)
        log_path = self.output_dir / f"{self.filename}_download.log"
        subtitle_sizes = {}

        with open(
            log_path,
            "a" if is_resume else "w",
            encoding="utf-8",
            errors="replace",
        ) as log_file:
            log_file.write(f"Command: {' '.join(cmd)}\n{'=' * 80}\n\n")

            # Unified progress bar manager (Rich in CLI, null-context in GUI)
            with DownloadBarManager(self.download_id) as bar_mgr:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    universal_newlines=True,
                )

                # Register process for potential termination
                if self.download_id:
                    download_tracker.register_process(self.download_id, proc)

                with proc:
                    stop_reason, auth_errors = self._monitor_download(
                        proc, log_file, log_parser, bar_mgr, subtitle_sizes
                    )

                # Ensure all tasks are complete
                bar_mgr.finish_all_tasks()

        self.exit_code = proc.returncode

        if is_resume:
            resume_dir = self._find_segment_dir(tmp_dir)
            resume_files = (
                self._contiguous_files(resume_dir) if resume_dir else []
            )
            # The first segment of the requested range must be present;
            # otherwise advancing would silently skip a segment.
            if resume_files and int(resume_files[0].stem) == int(resume_from):
                resume_count = len(resume_files)
            else:
                resume_count = 0
            base = {
                "resume_dir": str(resume_dir) if resume_dir else None,
                "resume_count": resume_count,
                "exit_code": proc.returncode,
            }
            if stop_reason == "cancelled" or (
                self.download_id and download_tracker.is_stopped(self.download_id)
            ):
                return {"error": "cancelled", **base}
            if stop_reason in ("stalled", "auth"):
                return {
                    "error": "download_failed",
                    "stalled": stop_reason == "stalled",
                    "token_expired": stop_reason == "auth" or auth_errors > 0,
                    "message": (
                        "Download stalled"
                        if stop_reason == "stalled"
                        else "Playlist/segment token rejected"
                    ),
                    **base,
                }
            if proc.returncode not in (0, None):
                return {
                    "error": "download_failed",
                    "token_expired": auth_errors > 0,
                    "message": self._format_failure(
                        proc.returncode, log_parser.errors
                    ),
                    "errors": [str(e) for e in log_parser.errors[-5:]],
                    **base,
                }
            return {"error": None, **base}

        # Check if we were cancelled
        if stop_reason == "cancelled" or (
            self.download_id and download_tracker.is_stopped(self.download_id)
        ):
            return {"error": "cancelled"}

        # Check for key retrieval errors (Succedde spesso quando parsa m3u8 che hanno bisogna di licenza, ma non ho ancora trovato un caso per implementare license per quel cazzo di m3u8 quindi amen va su failed).
        if any("Failed to get KEY" in error for error in log_parser.errors):
            self.status = {
                "error": "key_error",
                "message": "Failed to retrieve decryption key",
                "exit_code": proc.returncode,
            }
            return self.status

        # The watchdog aborts a frozen process. A frozen N_m3u8DL-RE never
        # exits on its own (it retries rejected signed URLs forever), so this
        # is the only way the HLS layer can refresh the URL and resume.
        if stop_reason in ("stalled", "auth"):
            self.status = {
                "error": "download_failed",
                "exit_code": proc.returncode,
                "message": (
                    "Download stalled: no progress for "
                    f"{_cfg_int('DOWNLOAD', 'hls_stall_timeout', default=60)}s"
                    if stop_reason == "stalled"
                    else "Download aborted: playlist/segment token rejected"
                ),
                "stalled": stop_reason == "stalled",
                "token_expired": stop_reason == "auth" or auth_errors > 0,
                "errors": [str(e) for e in log_parser.errors[-5:]],
            }
            return self.status

        # A non-zero exit code means the downloader aborted. Do not pretend the
        # partial files on disk are a successful download.
        if proc.returncode not in (0, None):
            self.status = {
                "error": "download_failed",
                "exit_code": proc.returncode,
                "message": self._format_failure(proc.returncode, log_parser.errors),
                "token_expired": self._looks_like_expired_token(log_parser.errors),
                "errors": [str(e) for e in log_parser.errors[-5:]],
            }
            # Final tracking is the caller's responsibility: the HLS layer may
            # refresh the URL and resume, so marking a failed history entry
            # here would prevent the eventual success from being recorded.
            return self.status

        self.status = self._get_download_status(subtitle_sizes, external_subs)
        self.status["exit_code"] = proc.returncode

        if self.key:
            # IL 99% delle volte n3u8dl riesce a fare tutto ma in quel 1% sti cazzi meglio fare double check anche se si perde tempo.
            self._manual_decrypt_check(self.status)
            print("")

        return self.status

    # ------------------------------------------------------------------
    # Download watchdog
    # ------------------------------------------------------------------
    @staticmethod
    def _url_expiry(url: Optional[str]) -> Optional[float]:
        """Return the signed URL expiry (epoch seconds) from its ``e`` param.

        StreamingCommunity's CDN signs playlists with ``e=<epoch_ms>``. The
        watchdog uses it to refresh/resume shortly after expiry instead of
        waiting for the full stall timeout. Unknown/invalid values are ignored.
        """
        if not url:
            return None
        try:
            query = parse_qs(urlparse(str(url)).query)
        except Exception:
            return None
        raw = (query.get("e") or [None])[0]
        if not raw or not str(raw).isdigit():
            return None
        value = int(raw)
        # Accept both epoch seconds and milliseconds.
        if value > 10_000_000_000:
            value = value / 1000.0
        now = time.time()
        if value < now - 3600 or value > now + 7 * 86400:
            return None
        return float(value)

    @staticmethod
    def _is_auth_error(line: str) -> bool:
        """True when N_m3u8DL-RE reports a rejected signed URL (401/403)."""
        return bool(_AUTH_ERROR_RE.search(line or ""))

    @staticmethod
    def _progress_signature(line: str):
        """Return a comparable snapshot of a progress line.

        N_m3u8DL-RE keeps printing the same progress line while it retries a
        dead URL. Comparing the values lets the watchdog tell real progress
        from a frozen download.
        """
        if not line.startswith(("Vid", "Aud", "Sub")):
            return None
        segment = SEGMENT_RE.search(line)
        size = SIZE_RE.search(line)
        percent = PERCENT_RE.search(line)
        if not (segment or size or percent):
            return None
        return (
            segment.group(0) if segment else None,
            size.group(0) if size else None,
            percent.group(1) if percent else None,
        )

    @staticmethod
    def _terminate_process(proc, force: bool = False) -> None:
        """Terminate a stuck downloader, escalating to kill if needed.

        ``force`` is used for watchdog aborts: a hard kill prevents
        N_m3u8DL-RE from cleaning up the already-downloaded segments, which
        are needed to resume.
        """
        try:
            if proc.poll() is not None:
                return
        except Exception:
            pass
        if force:
            try:
                proc.kill()
                proc.wait(timeout=5)
                return
            except Exception:
                pass
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
            return
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            pass

    def _monitor_download(
        self, proc, log_file, log_parser, bar_mgr, subtitle_sizes
    ) -> tuple[Optional[str], int]:
        """Read the process output while watching for stalls and auth errors.

        Returns ``(stop_reason, auth_error_count)``. ``stop_reason`` is one of
        ``None`` (process ended on its own), ``"cancelled"``, ``"stalled"`` or
        ``"auth"``.
        """
        output_queue: "queue.Queue" = queue.Queue()

        def _reader():
            try:
                for item in _read_download_output(proc.stdout):
                    output_queue.put(item)
            except Exception:
                pass
            finally:
                output_queue.put(_QUEUE_END)

        reader = threading.Thread(target=_reader, daemon=True)
        reader.start()

        stall_timeout = max(
            1, _cfg_int("DOWNLOAD", "hls_stall_timeout", default=60)
        )
        auth_error_limit = max(
            1, _cfg_int("DOWNLOAD", "hls_auth_error_limit", default=3)
        )
        last_change = time.monotonic()
        last_signature = None
        auth_errors = 0
        download_complete = False
        stop_reason: Optional[str] = None
        merge_timeout = max(stall_timeout, 15 * 60)

        expiry = self._url_expiry(getattr(self, "url", None))
        expiry_deadline = (
            time.monotonic() + max(0.0, expiry - time.time()) + _URL_EXPIRY_GRACE
            if expiry is not None
            else None
        )

        while True:
            if self.download_id and download_tracker.is_stopped(self.download_id):
                stop_reason = "cancelled"
                break

            try:
                item = output_queue.get(timeout=0.5)
            except queue.Empty:
                item = _QUEUE_EMPTY

            if item is _QUEUE_END:
                break

            if item is not _QUEUE_EMPTY:
                line, is_log = item

                is_log_line = is_log == "log" or any(
                    key in line for key in ("INFO :", "WARN :", "ERROR :")
                )
                if is_log_line:
                    log_file.write(line + "\n")
                    log_file.flush()
                    log_parser.parse_line(line)
                    # Progress lines can contain a segment index such as
                    # ``403/1804``; only real log lines may indicate auth
                    # failures.
                    if self._is_auth_error(line):
                        auth_errors += 1

                if any(
                    marker in line.lower()
                    for marker in ("binary merging", "start merging", "merging...")
                ):
                    download_complete = True
                    last_change = time.monotonic()

                signature = self._progress_signature(line)
                if signature is not None and signature != last_signature:
                    last_signature = signature
                    last_change = time.monotonic()
                    segments = signature[0]
                    if segments and "/" in segments:
                        try:
                            current, total = (
                                int(value) for value in segments.split("/", 1)
                            )
                            if total > 0 and current >= total:
                                download_complete = True
                                last_change = time.monotonic()
                        except (TypeError, ValueError):
                            pass

                self._parse_progress_line(line, bar_mgr, subtitle_sizes)

            if auth_errors >= auth_error_limit:
                stop_reason = "auth"
                break
            if (
                expiry_deadline is not None
                and not download_complete
                and time.monotonic() >= expiry_deadline
            ):
                # The signed URL is dead; do not wait for the longer stall
                # timeout. The HLS layer will refresh it and resume.
                stop_reason = "auth"
                break
            effective_timeout = merge_timeout if download_complete else stall_timeout
            if time.monotonic() - last_change > effective_timeout:
                stop_reason = "stalled"
                break

        if stop_reason is not None:
            self._terminate_process(
                proc, force=stop_reason in ("stalled", "auth")
            )

        reader.join(timeout=2)
        return stop_reason, auth_errors

    # ------------------------------------------------------------------
    # Segment-level resume
    # ------------------------------------------------------------------
    @staticmethod
    def _segment_files(directory: Path) -> List[Path]:
        """Numeric segment files in *directory*, ignoring partial ``.tmp``."""
        try:
            if not directory or not Path(directory).is_dir():
                return []
        except OSError:
            return []

        found = []
        for path in Path(directory).iterdir():
            try:
                if not path.is_file():
                    continue
            except OSError:
                continue
            if path.name.endswith(".tmp"):
                continue
            if path.suffix.lower() not in _SEGMENT_FILE_EXTS:
                continue
            if not path.stem.isdigit():
                continue
            found.append((int(path.stem), path))
        found.sort(key=lambda item: item[0])
        return [path for _, path in found]

    @classmethod
    def _contiguous_files(cls, directory: Path) -> List[Path]:
        """Numeric segment files from the start of *directory*, until a gap."""
        files = cls._segment_files(directory)
        if not files:
            return []
        result = [files[0]]
        for path in files[1:]:
            if int(path.stem) == int(result[-1].stem) + 1:
                result.append(path)
            else:
                break
        return result

    @classmethod
    def _find_segment_dir(cls, root) -> Optional[Path]:
        """Find the stream directory N_m3u8DL-RE wrote segments into."""
        if not root:
            return None
        root_path = Path(root)
        if not root_path.is_dir():
            return None

        candidates = []
        try:
            for path in root_path.rglob("*"):
                if path.is_dir() and cls._segment_files(path):
                    candidates.append(path)
        except OSError:
            pass
        if not candidates:
            return None

        # Prefer the first selected video stream, otherwise the newest dir.
        for candidate in candidates:
            if candidate.name.startswith("0__"):
                return candidate
        return max(candidates, key=lambda p: p.stat().st_mtime)

    def _load_selected_meta(self) -> Optional[list]:
        if not self.meta_selected_path:
            return None
        try:
            with open(
                self.meta_selected_path, encoding="utf-8-sig", errors="replace"
            ) as handle:
                data = json.load(handle)
        except Exception:
            return None
        return data if isinstance(data, list) else None

    def get_resume_plan(self) -> Optional[Dict[str, Any]]:
        """Describe how to resume a failed single-stream, clear TS download.

        Only the safe case is resumed: one selected video stream, unencrypted
        TS segments. Anything else falls back to a normal restart.
        """
        if self.audio_only or self.key:
            return None

        data = self._load_selected_meta()
        if not data or len(data) != 1:
            return None

        stream = data[0]
        if not stream.get("Resolution"):
            return None
        if str(stream.get("Extension") or "").lower() != "ts":
            return None

        codecs = str(stream.get("Codecs") or "")
        try:
            bandwidth = int(stream.get("Bandwidth") or 0)
        except (TypeError, ValueError):
            return None

        total_segments = 0
        first_index = None
        segment_indexes = []
        parts = (stream.get("Playlist") or {}).get("MediaParts") or []
        if len(parts) != 1:
            return None
        for part in parts:
            for segment in part.get("MediaSegments") or []:
                index = segment.get("Index")
                if not isinstance(index, int):
                    return None
                if first_index is None:
                    first_index = index
                segment_indexes.append(index)
                total_segments += 1
                encrypt = segment.get("EncryptInfo") or {}
                method = str(encrypt.get("Method") or "NONE").upper()
                if segment.get("IsEncrypted") or method not in ("", "NONE"):
                    return None
        if total_segments <= 0 or first_index is None:
            return None
        if segment_indexes != list(
            range(first_index, first_index + total_segments)
        ):
            return None

        prefix_dir = self.output_dir / self.filename / f"0__{codecs}_{bandwidth}_"
        if not prefix_dir.is_dir():
            # Fallback for slightly different sanitisation of the dir name.
            matches = []
            for root in (self.output_dir / self.filename, self.output_dir):
                if not root.is_dir():
                    continue
                try:
                    matches = [
                        path
                        for path in root.iterdir()
                        if path.is_dir()
                        and path.name.startswith("0__")
                        and codecs in path.name
                    ]
                except OSError:
                    matches = []
                if matches:
                    break
            if not matches:
                try:
                    matches = [
                        path
                        for path in self.output_dir.rglob(
                            f"0__{codecs}_{bandwidth}_"
                        )
                        if path.is_dir()
                    ]
                except OSError:
                    matches = []
            if len(matches) != 1:
                return None
            prefix_dir = matches[0]

        files = self._contiguous_files(prefix_dir)
        if not files:
            return None

        # N_m3u8DL-RE names segment files after their playlist index. If the
        # first one is missing we cannot safely know how much was downloaded.
        if int(files[0].stem) != first_index:
            return None

        return {
            "prefix_dir": str(prefix_dir),
            "first_index": first_index,
            "offset": len(files),
            "total": total_segments,
            "ext": "ts",
        }

    @staticmethod
    def _append_file(target, source: Path) -> None:
        with open(source, "rb") as src:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                target.write(chunk)

    def build_resumed_status(
        self,
        prefix_dir: Optional[str],
        parts: List[Dict[str, Any]],
        extension: str = "ts",
        total: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Concatenate the prefix and resumed segments into one TS file."""
        joined = self.output_dir / f"{self.filename}_joined.{extension}"
        written = 0

        def _can_write() -> bool:
            return total is None or written < total

        with open(joined, "wb") as target:
            if prefix_dir:
                for path in self._contiguous_files(Path(prefix_dir)):
                    if not _can_write():
                        break
                    self._append_file(target, path)
                    written += 1

            for part in parts:
                if not _can_write():
                    break
                part_dir = part.get("dir")
                if not part_dir:
                    continue
                try:
                    count = int(part.get("count") or 0)
                except (TypeError, ValueError):
                    count = 0
                if total is not None:
                    count = min(count, total - written)
                for path in self._contiguous_files(Path(part_dir))[:count]:
                    self._append_file(target, path)
                    written += 1

        if written == 0 or (total is not None and written < total):
            try:
                joined.unlink()
            except OSError:
                pass
            message = (
                "No downloaded segments to merge"
                if written == 0
                else f"Incomplete resume: {written}/{total} segments"
            )
            status = {
                "error": "download_failed",
                "message": message,
                "video": None,
                "audios": [],
                "subtitles": [],
                "external_subtitles": [],
            }
            self.status = status
            return status

        status = {
            "video": {"path": str(joined), "size": joined.stat().st_size},
            "audios": [],
            "subtitles": [],
            "external_subtitles": [],
        }
        self.status = status
        return status

    def _manual_decrypt_check(self, status: Dict[str, Any]):
        """Check and manually decrypt files if they are still encrypted after download"""
        print("")
        decryptor = Decryptor(preference=self.decrypt_preference)

        # Prepare targets with their respective stream types
        targets = []
        if status.get("video"):
            targets.append((status["video"], "video"))
        if status.get("audios"):
            for audio in status["audios"]:
                targets.append((audio, "audio"))

        keys = (
            self.key.get_keys_list()
            if isinstance(self.key, KeysManager)
            else ([self.key] if isinstance(self.key, str) else self.key)
        )
        for target, stream_type in targets:
            file_path = Path(target["path"])
            if not file_path.exists():
                continue

            # Check if still encrypted
            console.print(
                f"[cyan]Checking if file [red]{file_path.name} [cyan]is still encrypted..."
            )
            if decryptor.detect_encryption(str(file_path)):
                # Decrypt to a temporary file
                temp_output = file_path.with_suffix(file_path.suffix + ".decrypted")

                if decryptor.decrypt(
                    str(file_path), keys, str(temp_output), stream_type=stream_type
                ):
                    try:
                        # Replace the old file with the decrypted one
                        file_path.unlink()
                        temp_output.rename(file_path)

                        # Update status with new size
                        target["size"] = file_path.stat().st_size
                    except Exception as e:
                        console.print(
                            f"[red]Failed to replace encrypted file: {e}[/red]"
                        )
                        if temp_output.exists():
                            temp_output.unlink()
                else:
                    if temp_output.exists():
                        temp_output.unlink()
                    console.print(
                        f"[red]Manual decryption failed for: {file_path.name}[/red]"
                    )

            else:
                console.print("[dim]Not encrypted, copied")

    def _update_task(
        self, bar_mgr: DownloadBarManager, key: str, label: str, line: str
    ):
        """Parse a progress line and push the result to the unified bar manager."""
        cur_segment, cur_percent, cur_speed, cur_size = None, None, None, None

        if m := SEGMENT_RE.search(line):
            cur_segment = m.group(0)

        if m := PERCENT_RE.search(line):
            try:
                cur_percent = float(m.group(1))
            except Exception:
                pass

        if m := SPEED_RE.search(line):
            cur_speed = m.group(1)

        if m := SIZE_RE.search(line):
            cur_size = f"{m.group(1)}/{m.group(2)}"

        parsed = {
            "task_key": key,
            "label": f"[yellow]{self.manifest_type} {label}",
        }
        if cur_percent is not None:
            parsed["pct"] = cur_percent
        if cur_segment:
            parsed["segments"] = cur_segment
        if cur_speed:
            parsed["speed"] = cur_speed
        if cur_size:
            parsed["size"] = cur_size

        # Skip header/preview lines that carry no progress metrics yet.
        if any(k in parsed for k in ("pct", "segments", "speed", "size")):
            bar_mgr.handle_progress_line(parsed)
        return key

    def _parse_progress_line(
        self, line: str, bar_mgr: DownloadBarManager, subtitle_sizes: dict
    ):
        """
        Parse a progress line and update the unified progress bars"""
        if line.startswith("Vid"):
            res = (
                VIDEO_LINE_RE.search(line).group(1)
                if VIDEO_LINE_RE.search(line)
                else next(
                    (
                        s.resolution or s.extension or "main"
                        for s in self.streams
                        if s.type == "Video"
                    ),
                    "main",
                )
            )
            self._update_task(bar_mgr, f"video_{res}", f"[cyan]Vid [red]{res}", line)

        elif line.startswith("Aud"):
            if m := AUDIO_LINE_RE.search(line):
                bitrate, lang_name = m.group(1).strip(), m.group(2).strip()
                display = (
                    lang_name
                    if any(c.isalpha() for c in lang_name)
                    else next(
                        (
                            s.language or s.name or bitrate
                            for s in self.streams
                            if s.type == "Audio"
                            and s.bandwidth
                            and bitrate in s.bandwidth
                        ),
                        bitrate,
                    )
                )
                self._update_task(
                    bar_mgr,
                    f"audio_{lang_name}_{bitrate}",
                    f"[cyan]Aud [red]{display}",
                    line,
                )

        elif line.startswith("Sub"):
            if m := SUBTITLE_LINE_RE.search(line):
                lang, codec = m.group(1).strip(), m.group(2).strip()

                # SHIT Attempt to fix find actual language from streams if codec seems to be a tech type | TO REWRITE
                display_lang = lang
                if any(
                    x in lang.lower() for x in ["stpp", "ttml", "vtt", "srt"]
                ) or any(x in codec.lower() for x in ["stpp", "ttml", "vtt", "srt"]):
                    for s in self.streams:
                        # Check if codec matches and lang matches (as sub-string)
                        if (
                            s.type.lower().startswith("subtitle")
                            and s.codec
                            and (
                                any(
                                    x in s.codec.lower()
                                    for x in ["stpp", "ttml", "vtt", "srt"]
                                )
                            )
                        ):
                            s_lang = (s.language or "").lower()
                            p_lang = lang.lower()
                            if s_lang == p_lang or s_lang in p_lang or p_lang in s_lang:
                                if s.language:
                                    display_lang = s.language
                                    break

                # If still using tech name for display_lang, try to clean it
                display_lang = get_subtitle_codec_name(display_lang)
                self._update_task(
                    bar_mgr,
                    f"sub_{lang}_{codec}",
                    f"[cyan]Sub [red]{display_lang}",
                    line,
                )

                if fm := SUBTITLE_FINAL_SIZE_RE.search(line):
                    final_size = fm.group(1)
                    bar_mgr.handle_progress_line(
                        {
                            "task_key": f"sub_{lang}_{codec}",
                            "pct": 100,
                            "final_size": final_size,
                            "_lang_code": lang,
                            "codec": codec,
                        }
                    )
                    subtitle_sizes[f"{lang}: {codec}"] = final_size

                elif not SIZE_RE.search(line):
                    if sm := re.search(r"(\d+\.\d+(?:B|KB|MB|GB))\s*$", line):
                        subtitle_sizes[f"{lang}: {codec}"] = sm.group(1)

    def _extract_language_from_filename(self, filename: str, base_name: str) -> str:
        """Extract language from filename"""
        stem = (
            filename[len(base_name) :].lstrip(".")
            if filename.startswith(base_name)
            else filename
        )
        return stem.rsplit(".", 1)[0].split(".")[0] if "." in stem else stem

    def _get_download_status(
        self, subtitle_sizes: dict, external_subs: list
    ) -> Dict[str, Any]:
        """Get final download status"""
        status = {
            "video": None,
            "audios": [],
            "subtitles": [],
            "external_subtitles": external_subs,
        }
        exts = {
            "video": [".mp4", ".mkv", ".m4v", ".ts", ".mov", ".webm"],
            "audio": [".m4a", ".aac", ".mp3", ".ts", ".mp4", ".wav", ".webm"],
            "subtitle": [
                ".srt",
                ".vtt",
                ".ass",
                ".sub",
                ".ssa",
                ".m4s",
                ".ttml",
                ".xml",
            ],
        }

        # Find video
        for ext in exts["video"]:
            if (f := self.output_dir / f"{self.filename}{ext}").exists():
                status["video"] = {"path": str(f), "size": f.stat().st_size}
                break

        # Process downloaded subtitle metadata
        downloaded_subs = [
            {
                "lang": (d_name.split(":", 1)[0] if ":" in d_name else d_name).strip(),
                "name": (d_name.split(":", 1)[1] if ":" in d_name else d_name).strip(),
                "size": sz,
                "used": False,
            }
            for d_name, size_str in subtitle_sizes.items()
            if (sz := internet_manager.format_file_size(size_str))
        ]

        def norm_lang(lang):
            return set(lang.lower().replace("-", ".").split("."))

        seen_langs = {}

        # Scan files
        for f in sorted(list(self.output_dir.iterdir())):
            if not f.is_file():
                continue

            # Audio
            if any(f.name.lower().endswith(e) for e in exts["audio"]):
                if status["video"] and f.name == Path(status["video"]["path"]).name:
                    continue

                name = (
                    f.stem[len(self.filename) :].lstrip(".")
                    if f.stem.lower().startswith(self.filename.lower())
                    else f.stem
                )
                status["audios"].append(
                    {"path": str(f), "name": name, "size": f.stat().st_size}
                )

            # Subtitle
            elif any(f.name.lower().endswith(e) for e in exts["subtitle"]):
                ext_lang = self._extract_language_from_filename(f.stem, self.filename)
                f_size = f.stat().st_size
                best_sub, min_diff = None, float("inf")

                # Find best match
                f_lang_tokens = norm_lang(ext_lang)
                for sub in downloaded_subs:
                    if sub.get("used"):
                        continue

                    s_lang_tokens = norm_lang(sub["lang"])
                    overlap = f_lang_tokens & s_lang_tokens
                    diff = abs(sub["size"] - f_size)
                    if (
                        not f_lang_tokens or not s_lang_tokens or overlap
                    ) or not downloaded_subs:
                        if diff < min_diff and diff <= 2048:
                            min_diff, best_sub = diff, sub

                # Determine display name
                if best_sub:
                    lang, name = best_sub["lang"], best_sub["name"]
                    best_sub["used"] = True
                    final_name = (
                        f"{lang} - {name}"
                        if seen_langs.get(lang) and name and name != lang
                        else lang
                    )
                    seen_langs[lang] = seen_langs.get(lang, 0) + 1
                else:
                    final_name = ext_lang

                status["subtitles"].append(
                    {
                        "path": str(f),
                        "language": final_name,
                        "name": final_name,
                        "size": f_size,
                    }
                )

        return status

    def get_status(self) -> Dict[str, Any]:
        """Get current download status"""
        return self.status if self.status else self._get_download_status({}, [])
