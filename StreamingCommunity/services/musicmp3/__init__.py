# 28.08.26

from __future__ import annotations

from typing import Any

# External library
from rich.prompt import Prompt

# Internal utilities
from StreamingCommunity.services._base import EntriesManager
from StreamingCommunity.services._base.music_search_manager import (
    base_music_search,
    process_music_entry,
)
from StreamingCommunity.services._base.site_search_manager import get_select_title
from StreamingCommunity.services._base.site_costant import site_constants
from StreamingCommunity.utils import TVShowManager
from StreamingCommunity.utils.console.shared import console

# Logic
from . import scrapper
from .downloader import download_album, download_track

# Variable
indice = 20
_useFor = "Music"


msg = Prompt()
entries_manager = EntriesManager()
table_show_manager = TVShowManager()


def title_search_song(query: str) -> int:
    """Search individual songs and load them into the manager."""
    return _load(scrapper.search_songs(query))


def title_search_album(query: str) -> int:
    """Search albums and load them into the manager."""
    return _load(scrapper.search_albums(query))


def title_search_artist(query: str) -> int:
    """Search artists and load them into the manager."""
    return _load(scrapper.search_artists(query))


def _load(manager: EntriesManager) -> int:
    entries_manager.clear()
    table_show_manager.clear()
    for item in manager.media_list:
        entries_manager.add(item)
    return len(entries_manager)


def get_albums(artist) -> EntriesManager:
    return scrapper.get_albums(artist)


def get_tracks(album) -> EntriesManager:
    return scrapper.get_tracks(album)


def process_search_result(select_title, selections=None, scrape_serie=None) -> bool:
    """
    Route the selected music entry through the generic music drill-down flow.
    """
    return process_music_entry(
        select_title,
        get_albums_func=get_albums,
        get_tracks_func=get_tracks,
        download_track_func=download_track,
        download_album_func=lambda entry: download_album(entry, get_tracks),
        entries_manager=entries_manager,
        table_show_manager=table_show_manager,
    )


def search(
    string_to_search: str | None = None,
    get_onlyDatabase: bool = False,
    direct_item: dict | None = None,
    selections: dict | None = None,
    scrape_serie=None,
):
    """
    Music search and download entry point for musicmp3.ru.
    """
    return base_music_search(
        song_search_func=title_search_song,
        album_search_func=title_search_album,
        artist_search_func=title_search_artist,
        get_albums_func=get_albums,
        get_tracks_func=get_tracks,
        download_track_func=download_track,
        download_album_func=lambda entry: download_album(entry, get_tracks),
        entries_manager=entries_manager,
        table_show_manager=table_show_manager,
        site_name=site_constants.SITE_NAME,
        string_to_search=string_to_search,
        get_onlyDatabase=get_onlyDatabase,
        direct_item=direct_item,
    )
