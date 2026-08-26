# 17.10.24
from __future__ import annotations

import logging
import os
import shutil
import time
from typing import Any

# External libraries
from StreamingCommunity.core.processors import join_audios, join_subtitles, join_video
from StreamingCommunity.utils.console.shared import console
from StreamingCommunity.core.processors.helper.kodi_nfo import (
    KODI_NFO_FILES,
    generate_kodi_metadata,
)
from StreamingCommunity.core.processors.helper.nfo import create_nfo

# # Downloader
from StreamingCommunity.source.N_m3u8 import MediaDownloader
from StreamingCommunity.source.utils.media_players import MediaPlayers
from StreamingCommunity.source.utils.tracker import context_tracker, download_tracker

# Internal utilities
from StreamingCommunity.utils import config_manager, internet_manager, os_manager
from StreamingCommunity.utils.http_client import get_headers

# Config
CLEANUP_TMP = config_manager.config.get_bool("DOWNLOAD", "cleanup_tmp_folder")
EXTENSION_OUTPUT = config_manager.config.get("PROCESS", "extension")
SKIP_DOWNLOAD = config_manager.config.get_bool("DOWNLOAD", "skip_download")
CREATE_NFO_FILES = config_manager.config.get_bool(
    "PROCESS", "generate_nfo", default=False
)
MERGE_SUBTITLES = config_manager.config.get_bool(
    "PROCESS", "merge_subtitle", default=True
)
MERGE_AUDIO = config_manager.config.get_bool("PROCESS", "merge_audio", default=True)
logger = logging.getLogger(__name__)


class HLS_Downloader:
    def __init__(
        self,
        m3u8_url: str,
        output_path: str | None = None,
        headers: dict[str, str] | None = None,
        audio_only: bool = False,
    ):
        """
        Args:
            m3u8_url: Source M3U8 playlist URL
            output_path: Full path including filename and extension (e.g., /path/to/video.mp4)
            headers: Custom headers for requests
            audio_only: If True, download only the audio track (no video)
        """
        self.m3u8_url = str(m3u8_url).strip()
        self.custom_headers = headers
        if self.custom_headers is None:
            self.custom_headers = get_headers()

        self.audio_only = audio_only

        # Sanitize and validate output path
        if not output_path:
            output_path = f"download.{EXTENSION_OUTPUT}"

        self.output_path = os_manager.get_sanitize_path(output_path)
        if not self.output_path.endswith(f".{EXTENSION_OUTPUT}"):
            self.output_path += f".{EXTENSION_OUTPUT}"

        # Extract directory and filename components ONCE
        self.filename_base = os.path.splitext(os.path.basename(self.output_path))[0]
        self.output_dir = os.path.join(
            os.path.dirname(self.output_path), self.filename_base + "_hls_temp"
        )
        self.file_already_exists = os.path.exists(self.output_path)

        # Tracking IDs - check context if not provided
        self.download_id = context_tracker.download_id
        self.site_name = context_tracker.site_name

        # Status tracking
        self.error = None
        self.last_merge_result = None
        self.media_players = None
        self.copied_subtitles = []
        self.copied_audios = []

    def start(self) -> tuple[str | None, Any]:
        """Main execution flow for downloading HLS content"""
        if self.file_already_exists:
            console.print("[yellow]File already exists.")
            return self.output_path, False

        # Setup media downloader
        self.media_downloader = MediaDownloader(
            url=self.m3u8_url,
            output_dir=self.output_dir,
            filename=self.filename_base,
            headers=self.custom_headers,
            download_id=self.download_id,
            site_name=self.site_name,
            audio_only=self.audio_only,
        )
        console.print("[dim]Parsing HLS ...")
        self.media_downloader.parser_stream()

        # Create output directory
        os_manager.create_path(self.output_dir)

        if SKIP_DOWNLOAD:
            console.print("[yellow]Skipping download as per configuration.")
            return self.output_path, False

        # Create media player ignore files to prevent media scanners
        try:
            self.media_players = MediaPlayers(self.output_dir)
            self.media_players.create()
        except ValueError:
            pass

        if self.download_id:
            download_tracker.update_status(self.download_id, "downloading")

        console.print("[dim]Starting download ...")
        status = self.media_downloader.start_download()

        # Check for cancellation
        if status.get("error") == "cancelled":
            if self.download_id:
                download_tracker.complete_download(
                    self.download_id, success=False, error="cancelled"
                )
            return None, True

        # Check if any media was downloaded
        if self._no_media_downloaded(status):
            logger.error("No media downloaded")
            if self.download_id:
                download_tracker.complete_download(
                    self.download_id, success=False, error="No media downloaded"
                )
            return None, True

        # Merge files using FFmpeg
        if self.download_id:
            download_tracker.update_status(self.download_id, "Muxing...")
        final_file = self._merge_files(status)

        if not final_file or not os.path.exists(final_file):
            if self.download_id and download_tracker.is_stopped(self.download_id):
                download_tracker.complete_download(
                    self.download_id, success=False, error="cancelled"
                )
                return None, True

            logger.error("Merge operation failed")
            if self.download_id:
                download_tracker.complete_download(
                    self.download_id, success=False, error="Merge failed"
                )
            return None, True

        # Move to final location if needed
        if os.path.abspath(final_file) != os.path.abspath(self.output_path):
            last_exc = None
            for attempt in range(10):
                try:
                    os.replace(final_file, self.output_path)
                    last_exc = None
                    break
                except (PermissionError, OSError) as e:
                    last_exc = e
                    console.log(f"[yellow]Rename attempt {attempt + 1}/10 failed: {e}")
                    time.sleep(0.5)
                    import gc

                    gc.collect()

            if last_exc:
                console.print(f"[yellow]Warning: Could not move file: {last_exc}")
                self.output_path = final_file

        # Move subtitle files if any were copied without merging
        self._move_copied_subtitles()

        # Move audio files if any were copied without merging
        self._move_copied_audios()

        # Print summary and cleanup
        self._print_summary()

        if CREATE_NFO_FILES:
            create_nfo(self.output_path)
        if KODI_NFO_FILES:
            generate_kodi_metadata(
                self.output_path, media_type=context_tracker.media_type
            )
        if self.download_id:
            download_tracker.complete_download(
                self.download_id, success=True, path=os.path.abspath(self.output_path)
            )

        if CLEANUP_TMP:
            shutil.rmtree(self.output_dir, ignore_errors=True)
        return self.output_path, False

    def _no_media_downloaded(self, status):
        """Check if no media was downloaded."""
        return (
            status.get("video") is None
            and status.get("audios") == []
            and status.get("subtitles") == []
            and status.get("external_subtitles") == []
        )

    def _merge_files(self, status) -> str | None:
        """Merge downloaded files using FFmpeg"""
        if status["video"] is None:
            # Audio-only mode: no video, but audio tracks exist
            if self.audio_only and status.get("audios"):
                audio_file = (
                    status["audios"][0].get("path")
                    if isinstance(status["audios"][0], dict)
                    else None
                )
                if not audio_file:
                    # Fallback: search for the largest audio file in the output dir
                    for f in os.listdir(self.output_dir):
                        if f.endswith((".m4a", ".aac", ".mp4", ".ts")):
                            audio_file = os.path.join(self.output_dir, f)
                            break
                if audio_file and os.path.exists(audio_file):
                    console.print(
                        f"[cyan]Audio-only mode: using {os.path.basename(audio_file)}"
                    )
                    shutil.copy2(audio_file, self.output_path)
                    return self.output_path
            return None

        video_path = status["video"].get("path")

        if not os.path.exists(video_path):
            console.print(f"[red]Video file not found: {video_path}")
            self.error = "Video file missing"
            return None

        # If no additional tracks, mux video using join_video
        if not status["audios"] and not status["subtitles"]:
            console.print("[cyan]\nNo additional tracks to merge, muxing video...")
            merged_file, result_json = join_video(
                video_path=video_path,
                out_path=self.output_path,
                log_path=os.path.join(self.output_dir, "video_mux.log"),
            )
            self.last_merge_result = result_json
            if os.path.exists(merged_file):
                return merged_file
            else:
                self.error = "Video mux failed"
                return None

        current_file = video_path

        # Merge or track audio tracks
        if status["audios"]:
            if MERGE_AUDIO:
                console.print(
                    f"[cyan]\nMerging [red]{len(status['audios'])} [cyan]audio track(s)..."
                )
                audio_output = os.path.join(
                    self.output_dir,
                    f"{self.filename_base}_with_audio.{EXTENSION_OUTPUT}",
                )

                merged_file, _use_shortest, result_json = join_audios(
                    video_path=current_file,
                    audio_tracks=status["audios"],
                    out_path=audio_output,
                    log_path=os.path.join(self.output_dir, "audio_merge.log"),
                )
                self.last_merge_result = result_json

                if os.path.exists(merged_file):
                    current_file = merged_file
                else:
                    console.print(
                        "[yellow]Audio merge failed, continuing with video only"
                    )
            else:
                console.print("[cyan]Track audio tracks.")
                self._track_audios_for_copy(status["audios"])

        # Merge subtitles if enabled and present
        if status["subtitles"]:
            if MERGE_SUBTITLES:
                console.print(
                    f"[cyan]\nMerging [red]{len(status['subtitles'])} [cyan]subtitle track(s)..."
                )
                sub_output = os.path.join(
                    self.output_dir, f"{self.filename_base}_final.{EXTENSION_OUTPUT}"
                )

                merged_file, result_json = join_subtitles(
                    video_path=current_file,
                    subtitles_list=status["subtitles"],
                    out_path=sub_output,
                    log_path=os.path.join(self.output_dir, "sub_merge.log"),
                )
                self.last_merge_result = result_json

                if os.path.exists(merged_file):
                    current_file = merged_file
                else:
                    console.print(
                        "[yellow]Subtitle merge failed, continuing without subtitles"
                    )
            else:
                self._track_subtitles_for_copy(status["subtitles"])

        return current_file

    def _track_subtitles_for_copy(self, subtitles_list):
        """Track subtitle paths for later copying to final location."""
        for idx, subtitle in enumerate(subtitles_list):
            sub_path = subtitle.get("path")
            if sub_path and os.path.exists(sub_path):
                language = subtitle.get("language", f"sub{idx}")
                extension = os.path.splitext(sub_path)[1]
                self.copied_subtitles.append(
                    {"src": sub_path, "language": language, "extension": extension}
                )

    def _track_audios_for_copy(self, audios_list):
        """Track audio paths for later copying to final location."""
        for idx, audio in enumerate(audios_list):
            audio_path = audio.get("path")
            if audio_path and os.path.exists(audio_path):
                language = audio.get("language", f"audio{idx}")
                extension = os.path.splitext(audio_path)[1]
                self.copied_audios.append(
                    {"src": audio_path, "language": language, "extension": extension}
                )

    def _move_copied_subtitles(self):
        """Move tracked subtitle files to final output directory if copied_subtitles exits."""
        if not self.copied_subtitles:
            return

        output_dir = os.path.dirname(self.output_path)
        filename_base = os.path.splitext(os.path.basename(self.output_path))[0]
        console.print("[cyan]Copy the subtitles to the final path.")

        for sub_info in self.copied_subtitles:
            src_path = sub_info["src"]
            language = sub_info["language"]
            extension = sub_info["extension"]

            # final name
            dst_path = os.path.join(
                output_dir, f"{filename_base}.{language}{extension}"
            )

            try:
                shutil.copy2(src_path, dst_path)
            except OSError as e:
                logger.error(
                    f"[yellow]Warning: Could not move subtitle {language}: {e}"
                )

    def _move_copied_audios(self):
        """Move tracked audio files to final output directory if copied_audios exists."""
        if not self.copied_audios:
            return

        output_dir = os.path.dirname(self.output_path)
        filename_base = os.path.splitext(os.path.basename(self.output_path))[0]
        console.print("[cyan]Copy the audios to the final path.")

        for audio_info in self.copied_audios:
            src_path = audio_info["src"]
            language = audio_info["language"]
            extension = audio_info["extension"]

            # final name
            dst_path = os.path.join(
                output_dir, f"{filename_base}.{language}{extension}"
            )

            try:
                shutil.copy2(src_path, dst_path)
            except OSError as e:
                logger.error(f"[yellow]Warning: Could not move audio {language}: {e}")

    def _print_summary(self):
        """Print download summary"""
        if not os.path.exists(self.output_path):
            return

        file_size = internet_manager.format_file_size(os.path.getsize(self.output_path))
        duration = "N/A"

        if self.last_merge_result and isinstance(self.last_merge_result, dict):
            duration = self.last_merge_result.get("time", "N/A")

        console.print("\n[green]Output:")
        console.print(f"  [cyan]Path: [red]{os.path.abspath(self.output_path)}")
        console.print(f"  [cyan]Size: [red]{file_size}")
        console.print(f"  [cyan]Duration: [red]{duration}")
