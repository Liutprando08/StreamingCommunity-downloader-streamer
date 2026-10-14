# Downloader for https://monochrome.st (music)
#
# Tracks are served as a plain, DRM-free file from:
#   https://tracks.monochrome.st/track/{trackId}
# The container varies (MP4/M4A AAC, occasionally FLAC/Ogg/MP3), so the file
# extension is derived from the response Content-Type, with a magic-byte peek
# as a fallback.

from __future__ import annotations

# Internal utilities
from StreamingCommunity.services._base import Entries
from StreamingCommunity.services._base.music_downloader import (
    TrackDownloadReporter,
    music_output_path,
)
from StreamingCommunity.utils.console.shared import console
from StreamingCommunity.utils.http_client import create_client

# Variables
STREAM_HEADERS = {
    "Accept": "*/*",
    "Referer": "https://monochrome.st/",
    "Origin": "https://monochrome.st",
}

_EXT_BY_TYPE = {
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/m4a": ".m4a",
    "audio/aac": ".aac",
    "audio/flac": ".flac",
    "audio/x-flac": ".flac",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
}


def _sniff_extension(head: bytes) -> str | None:
    """Guess the container from the first bytes of the response."""
    if head[:4] == b"fLaC":
        return ".flac"
    if head[:4] == b"OggS":
        return ".ogg"
    if head[:3] == b"ID3" or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return ".mp3"
    if head[:4] == b"RIFF":
        return ".wav"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return ".m4a"
    return None


def _extension(content_type: str | None, head: bytes) -> str:
    """Pick the output extension from the Content-Type, then magic bytes."""
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime in _EXT_BY_TYPE:
        return _EXT_BY_TYPE[mime]
    return _sniff_extension(head) or ".m4a"


def download_track(entry: Entries) -> str | None:
    """
    Download a single track to the music library folder and return its path.
    """
    stream_url = entry.url
    console.print(f"\n[yellow]Download: [red]monochrome [cyan]{entry.name}")

    reporter = TrackDownloadReporter(entry)
    reporter.start()

    if not stream_url:
        console.print(f"[red]monochrome: missing stream URL for {entry.name}")
        reporter.complete(success=False, error="missing stream URL")
        return None

    try:
        with (
            create_client(
                headers=STREAM_HEADERS, timeout=60, follow_redirects=True
            ) as client,
            client.stream("GET", stream_url) as response,
        ):
            response.raise_for_status()
            total = int(response.headers.get("Content-Length") or 0)
            chunks = response.iter_bytes(chunk_size=65536)

            # Peek the first chunk to sniff the container before choosing the
            # filename; the Content-Type header is the primary signal.
            first = next(chunks, b"")
            output_path = music_output_path(
                entry, extension=_extension(response.headers.get("Content-Type"), first)
            )

            downloaded = 0
            with open(output_path, "wb") as file:
                if first:
                    file.write(first)
                    downloaded += len(first)
                    reporter.progress(downloaded, total)
                for chunk in chunks:
                    if chunk:
                        file.write(chunk)
                        downloaded += len(chunk)
                        reporter.progress(downloaded, total)
    except Exception as e:
        console.print(f"[red]monochrome: error downloading {entry.name}: {e}")
        reporter.complete(success=False, error=str(e))
        return None

    reporter.complete(success=True, path=output_path)
    console.print(f"[green]Downloaded: [white]{output_path}")
    return output_path


def download_album(entry: Entries, get_tracks_func) -> bool:
    """
    Download every track of an album.
    """
    tracks = get_tracks_func(entry)
    if len(tracks) <= 0:
        console.print(f"[red]No tracks found for {entry.name}")
        return False

    downloads = 0
    for track in tracks.media_list:
        path = download_track(track)
        if path:
            downloads += 1

    console.print(
        f"\n[green]Album download finished: {downloads}/{len(tracks)} tracks"
    )
    return downloads > 0
