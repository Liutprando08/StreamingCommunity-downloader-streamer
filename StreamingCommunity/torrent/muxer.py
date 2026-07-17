# 2026

from typing import Optional, List


class TorrentMuxer:
    """Mux torrent video + streaming audio/subs via ffmpeg."""

    def __init__(self, config_manager): ...

    def mux(
        self,
        video_path: str,
        audio_paths: Optional[List[str]] = None,
        subtitle_paths: Optional[List[str]] = None,
        output_path: Optional[str] = None,
    ) -> Optional[str]: ...

    def detect_streams(self, file_path: str) -> dict: ...
