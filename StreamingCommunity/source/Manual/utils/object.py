# 19.05.25

from dataclasses import dataclass, field

# Internal utilities
from .drm_info import DRMInfo


@dataclass
class Segment:
    url: str
    number: int
    type: str = "media"
    size: int = 0
    downloaded: bool = False

    def __repr__(self):
        return f"Segment({self.number}, {self.type})"


@dataclass
class Stream:
    type: str
    id: str | None = None
    segments: list = field(default_factory=list)
    bitrate: int = 0
    language: str = "und"
    resolution: str = "unknown"
    width: int = 0
    height: int = 0
    fps: str = "unknown"
    codecs: str = "unknown"
    name: str = "unknown"
    role: str = "main"
    drm: DRMInfo = field(default_factory=DRMInfo)
    encryption_method: str | None = None
    key_uri: str | None = None
    key_data: str | None = None
    iv: str | None = None
    selected: bool = False
    duration: float = 0
    playlist_url: str | None = None

    def add_segment(self, segment):
        self.segments.append(segment)

    def get_description(self):
        if self.type == "video":
            return f"video_{self.resolution}"
        elif self.type == "audio":
            return f"audio_{self.language}"
        elif self.type == "image":
            return f"thumbnail_{self.resolution}"
        else:
            return f"subtitle_{self.language}"

    def get_type_display(self):
        if self.type == "video":
            return "Video"
        elif self.type == "audio":
            return "Audio"
        elif self.type == "image":
            return "Thumbnail"
        else:
            return "Subtitle"

    def get_duration_display(self):
        if self.duration > 0:
            minutes = int(self.duration // 60)
            seconds = int(self.duration % 60)
            return f"{minutes:02d}:{seconds:02d}"
        return "-"

    def __repr__(self):
        drm_str = f", {self.drm.drm_type}" if self.drm.is_encrypted() else ""
        return f"Stream({self.type}, {self.get_description()}, {len(self.segments)} segments{drm_str})"