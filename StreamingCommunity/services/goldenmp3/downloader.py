# 28.08.26

from __future__ import annotations

from httpx2 import HTTPError

# Internal utilities
from StreamingCommunity.services._base import Entries
from StreamingCommunity.services._base.music_downloader import music_output_path
from StreamingCommunity.utils.console.shared import console
from StreamingCommunity.utils.http_client import create_client, get_userAgent

STREAM_HEADERS = {
    "Host": "listen.musicmp3.ru",
    "User-Agent": get_userAgent(),
    "Accept": (
        "audio/webm,audio/ogg,audio/wav,audio/*;q=0.9,"
        "application/ogg;q=0.7,video/*;q=0.6,*/*;q=0.5"
    ),
    "Referer": "https://musicmp3.ru/",
}


def download_track(entry: Entries) -> str | None:
    """
    Download a single track to the music library folder and return its path.
    """
    stream_url = entry.url
    output_path = music_output_path(entry)

    console.print(f"\n[yellow]Download: [red]goldenmp3 [cyan]{entry.name}")

    try:
        if stream_url is not None:
            with (
                create_client(
                    headers=STREAM_HEADERS, timeout=60, follow_redirects=True
                ) as client,
                client.stream("GET", stream_url) as response,
            ):
                response.raise_for_status()
                with open(output_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
    except HTTPError as e:
        console.print(f"[red]Error downloading {entry.name}: {e}")
        return None

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

    console.print(f"\n[green]Album download finished: {downloads}/{len(tracks)} tracks")
    return downloads > 0
