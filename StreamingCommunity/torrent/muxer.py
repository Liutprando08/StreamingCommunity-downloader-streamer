# 2026

import json
import os
import shutil
import logging
import subprocess
from typing import Optional, List, Dict


# External library
from rich.console import Console


# Internal utilities (lazy to avoid circular imports via torrent/__init__.py)
from StreamingCommunity.core.processors.capture import capture_ffmpeg_real_time


# Variable
console = Console()
log = logging.getLogger(__name__)


class TorrentMuxer:
    """Mux torrent video + streaming audio via ffmpeg."""

    def __init__(self):
        from StreamingCommunity.setup import get_ffmpeg_path, get_ffprobe_path
        self.ffmpeg_path = get_ffmpeg_path()
        self.ffprobe_path = get_ffprobe_path()

    def detect_streams(self, file_path: str) -> Dict[str, list]:
        """
        Use ffprobe to detect available streams in a media file.

        Returns:
            dict with keys 'video', 'audio', 'subtitle', each a list of stream dicts.
        """
        if not os.path.isfile(file_path):
            log.warning("File not found for stream detection: %s", file_path)
            return {"video": [], "audio": [], "subtitle": []}

        try:
            cmd = [
                self.ffprobe_path,
                "-v", "error",
                "-show_streams",
                "-print_format", "json",
                file_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                log.warning("ffprobe failed: %s", result.stderr.strip())
                return {"video": [], "audio": [], "subtitle": []}

            data = json.loads(result.stdout)
            streams = data.get("streams", [])

            classified = {"video": [], "audio": [], "subtitle": []}
            for stream in streams:
                codec_type = stream.get("codec_type", "")
                if codec_type in classified:
                    classified[codec_type].append(stream)

            return classified

        except Exception as e:
            log.error("Stream detection failed: %s", e)
            return {"video": [], "audio": [], "subtitle": []}

    def mux_video_audio(
        self,
        video_path: str,
        audio_source_path: str,
        output_path: str,
    ) -> Optional[str]:
        """
        Mux video from one file with audio from another using ffmpeg.

        Takes video track from video_path (input 0) and audio track from
        audio_source_path (input 1), producing a single output file.

        Parameters:
            video_path: Path to the file containing the video track (e.g., torrent download).
            audio_source_path: Path to the file containing the audio track (e.g., StreamingCommunity download).
            output_path: Path for the output file.

        Returns:
            str: output_path on success, None on failure.
        """
        if not os.path.isfile(video_path):
            console.print(f"[red]Video file not found: {video_path}")
            return None

        if not os.path.isfile(audio_source_path):
            console.print(f"[red]Audio source file not found: {audio_source_path}")
            return None

        video_size = os.path.getsize(video_path)
        audio_size = os.path.getsize(audio_source_path)
        required_bytes = video_size + audio_size + (100 * 1024 * 1024)

        try:
            usage = shutil.disk_usage(os.path.dirname(output_path) or ".")
            if usage.free < required_bytes:
                free_gb = usage.free / (1024 ** 3)
                need_gb = required_bytes / (1024 ** 3)
                console.print(f"[red]Insufficient disk space for mux: {free_gb:.1f} GB free, ~{need_gb:.1f} GB required")
                return None
        except Exception as e:
            log.warning("Disk space check failed: %s", e)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        # Detect how many audio streams the torrent file has
        original_audio_count = len(self.detect_streams(video_path).get("audio", []))

        ffmpeg_cmd = [self.ffmpeg_path]

        ffmpeg_cmd.extend(["-i", video_path])
        ffmpeg_cmd.extend(["-i", audio_source_path])

        ffmpeg_cmd.extend(["-map", "0:v"])
        ffmpeg_cmd.extend(["-map", "0:a?"])
        ffmpeg_cmd.extend(["-map", "1:a"])

        # Set metadata only on the Italian audio track(s)
        italian_audio_start = original_audio_count
        italian_streams = self.detect_streams(audio_source_path).get("audio", [])
        for i in range(len(italian_streams)):
            idx = italian_audio_start + i
            ffmpeg_cmd.extend([f"-metadata:s:a:{idx}", "language=ita"])
            ffmpeg_cmd.extend([f"-metadata:s:a:{idx}", "title=Italian"])

        ffmpeg_cmd.extend(["-c:v", "copy", "-c:a", "copy"])

        # Force interleaving so the added audio is written alongside the video
        # instead of being buffered and dumped at the end of the file.
        ffmpeg_cmd.extend(["-max_interleave_delta", "0"])

        ffmpeg_cmd.extend([output_path, "-y"])

        console.print(f"[yellow]FFMPEG [cyan]Muxing torrent video + original audio ({original_audio_count} tracks) + Italian audio...")
        result_json = capture_ffmpeg_real_time(
            ffmpeg_cmd,
            "[yellow]FFMPEG [cyan]Audio dub",
        )
        print()

        if os.path.isfile(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            console.print(f"[green]Mux complete: {output_path} ({size_mb:.1f} MB)")
            return output_path

        console.print("[red]Mux failed — output file not created")
        return None
