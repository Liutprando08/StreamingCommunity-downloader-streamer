# 28.08.26

from __future__ import annotations

# External library
from rich.prompt import Prompt

# Internal utilities
from StreamingCommunity.services._base import EntriesManager
from StreamingCommunity.services._base.music_search_manager import base_music_search
from StreamingCommunity.services._base.site_costant import site_constants
from StreamingCommunity.utils import TVShowManager

# Logic
from . import scrapper
from .downloader import download_album, download_track

# Variable
indice = 21
_useFor = "Music"


msg = Prompt()
entries_manager = EntriesManager()
table_show_manager = TVShowManager()


def title_search_album(query: str) -> int:
    """Search albums and load them into the manager."""
    entries_manager.clear()
    table_show_manager.clear()
    manager = scrapper.search_albums(query)
    for item in manager.media_list:
        entries_manager.add(item)
    return len(entries_manager)


# goldenmp3 exposes only reliable album search; keep the song/artist hooks
# bound to the same album search so the shared flow stays generic.
def title_search_song(query: str) -> int:
    return title_search_album(query)


def title_search_artist(query: str) -> int:
    return title_search_album(query)


def get_tracks(album) -> EntriesManager:
    return scrapper.get_tracks(album)


def get_albums(artist) -> EntriesManager:
    return EntriesManager()


def process_search_result(select_title, selections=None, scrape_serie=None) -> bool:
    if select_title is None:
        return False
    from StreamingCommunity.services._base.music_search_manager import (
        process_music_entry,
    )

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
    Music search and download entry point for goldenmp3.ru (album oriented).
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
        modes=("Album",),
    )
