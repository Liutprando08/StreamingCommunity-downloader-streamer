# 28.08.26

from __future__ import annotations

import os

# Internal utilities
from StreamingCommunity.services._base import Entries, site_constants
from StreamingCommunity.utils import os_manager
from StreamingCommunity.utils.console.shared import console


def music_filename(entry: Entries) -> str:
    """
    Build a sanitized .mp3 filename for a track entry.
    """
    artist = str(getattr(entry, "artist", "") or getattr(entry, "album_artist", "") or "Unknown")
    name = str(getattr(entry, "name", "") or "track")
    return f"{os_manager.get_sanitize_file(artist)} - {os_manager.get_sanitize_file(name)}.mp3"


def music_output_path(entry: Entries) -> str:
    """
    Build the output folder based on artist / album metadata.
    """
    base = site_constants.MUSIC_FOLDER
    artist = str(getattr(entry, "artist", "") or getattr(entry, "album_artist", "") or "Unknown")
    album = str(getattr(entry, "album", "") or "Single")

    folder = os.path.join(base, os_manager.get_sanitize_file(artist))
    if album and album.lower() != "single":
        folder = os.path.join(folder, os_manager.get_sanitize_file(album))

    os_manager.create_path(folder)
    return os.path.join(folder, music_filename(entry))
