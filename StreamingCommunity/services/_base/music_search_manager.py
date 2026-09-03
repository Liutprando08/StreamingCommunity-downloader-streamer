# 28.08.26

from __future__ import annotations

from typing import Any, Callable

# External library
from rich.prompt import Prompt

# Internal utilities
from StreamingCommunity.services._base import Entries, EntriesManager
from StreamingCommunity.services._base.site_search_manager import get_select_title
from StreamingCommunity.utils import TVShowManager
from StreamingCommunity.utils.console.shared import console

# Variable
msg = Prompt()

SEARCH_MODES = ("Song", "Album", "Artist")


def ask_search_mode(modes: tuple[str, ...] = SEARCH_MODES) -> str:
    """
    Ask the user what kind of media to search for (song / album / artist).
    """
    if len(modes) == 1:
        return modes[0]

    console.print("\n[cyan]What do you want to search for?")
    for i, mode in enumerate(modes, 1):
        console.print(f"[green]{i}. {mode}")
    choice = msg.ask(
        "[green]Insert choice (1-3)",
        choices=[str(i) for i in range(1, len(modes) + 1)],
        default="1",
        show_choices=False,
    )
    return modes[int(choice) - 1]


def select_tracks_to_download(
    entries_manager: EntriesManager, table_show_manager: TVShowManager
) -> list[Entries]:
    """
    Display the track list and let the user pick tracks (single, '*', or range).
    """
    if not entries_manager.media_list:
        console.print("[red]No tracks available.")
        return []

    table_show_manager.clear()
    get_select_title(table_show_manager, entries_manager)

    last_command = msg.ask(
        "\n[cyan]Insert track [red]index [yellow]or [red]* [cyan]to download all tracks "
        "[yellow]or [red]1-3 [cyan]for a range of tracks [yellow]or [red]q [cyan]to cancel",
    )

    if last_command.lower() in ("q", "quit"):
        console.print("\n[red]Selection cancelled.")
        return []

    if last_command == "*":
        return list(entries_manager.media_list)

    selected: list[Entries] = []
    for part in str(last_command).replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-")
            start, end = int(start_s), int(end_s)
            for i in range(start, end + 1):
                if 1 <= i <= len(entries_manager.media_list):
                    selected.append(entries_manager.media_list[i - 1])
        elif part.isdigit():
            i = int(part)
            if 1 <= i <= len(entries_manager.media_list):
                selected.append(entries_manager.media_list[i - 1])
        else:
            console.print(f"[red]Ignoring invalid selection: {part}")

    return selected


def base_music_search(
    song_search_func: Callable[[str], int],
    album_search_func: Callable[[str], int] | None,
    artist_search_func: Callable[[str], int] | None,
    get_albums_func: Callable[[Entries], EntriesManager] | None,
    get_tracks_func: Callable[[Entries], EntriesManager],
    download_track_func: Callable[[Entries], Any],
    download_album_func: Callable[[Entries], Any] | None,
    entries_manager: EntriesManager,
    table_show_manager: TVShowManager,
    site_name: str,
    string_to_search: str | None = None,
    get_onlyDatabase: bool = False,
    direct_item: dict[str, Any] | None = None,
    modes: tuple[str, ...] = SEARCH_MODES,
) -> Any:
    """
    Music-oriented search and download flow.

    Handles three modes (song / album / artist) and the artist -> album ->
    track drill-down. Returns EntriesManager when get_onlyDatabase=True,
    True/False otherwise.
    """
    if direct_item:
        entries_manager.clear()
        entry = Entries(**direct_item)
        return process_music_entry(
            entry,
            get_albums_func=get_albums_func,
            get_tracks_func=get_tracks_func,
            download_track_func=download_track_func,
            download_album_func=download_album_func,
            entries_manager=entries_manager,
            table_show_manager=table_show_manager,
        )

    # Collect the query from arguments or prompt the user
    actual_search_query = None
    if string_to_search is not None:
        actual_search_query = string_to_search.strip()
    else:
        actual_search_query = msg.ask(
            f"\n[purple]Insert a word to search in [green]{site_name}"
        ).strip()

    if not actual_search_query:
        return False

    mode = ask_search_mode(modes)

    # Route to the right search callback
    if mode == "Song":
        if not song_search_func:
            console.print("[red]Song search not supported on this site.")
            return False
        len_database = song_search_func(actual_search_query)
    elif mode == "Album":
        if not album_search_func:
            console.print("[red]Album search not supported on this site.")
            return False
        len_database = album_search_func(actual_search_query)
    else:
        if not artist_search_func:
            console.print("[red]Artist search not supported on this site.")
            return False
        len_database = artist_search_func(actual_search_query)

    entries_manager.sort_by_fuzzy_score(actual_search_query)

    if get_onlyDatabase:
        return entries_manager

    if len_database <= 0:
        console.print(
            f"\n[red]Nothing matching was found for[white]: [purple]{actual_search_query}"
        )
        return False

    selected = get_select_title(table_show_manager, entries_manager)
    if selected is None:
        return False

    return process_music_entry(
        selected,
        get_albums_func=get_albums_func,
        get_tracks_func=get_tracks_func,
        download_track_func=download_track_func,
        download_album_func=download_album_func,
        entries_manager=entries_manager,
        table_show_manager=table_show_manager,
    )


def process_music_entry(
    entry: Entries,
    get_albums_func: Callable[[Entries], EntriesManager] | None,
    get_tracks_func: Callable[[Entries], EntriesManager],
    download_track_func: Callable[[Entries], Any],
    download_album_func: Callable[[Entries], Any] | None,
    entries_manager: EntriesManager,
    table_show_manager: TVShowManager,
) -> bool:
    """
    Route a music entry to the appropriate next step (drill-down or download).
    """
    etype = str(getattr(entry, "type", "")).lower()

    if etype == "artist":
        if not get_albums_func:
            console.print("[red]Album listing not supported on this site.")
            return False
        entries_manager.clear()
        table_show_manager.clear()
        album_manager = get_albums_func(entry)
        if len(album_manager) <= 0:
            console.print(f"[red]No albums found for {entry.name}")
            return False
        album_manager.sort_by_fuzzy_score(str(getattr(entry, "name", "")))
        album = get_select_title(table_show_manager, album_manager)
        if album is None:
            return False
        return process_music_entry(
            album,
            get_albums_func=get_albums_func,
            get_tracks_func=get_tracks_func,
            download_track_func=download_track_func,
            download_album_func=download_album_func,
            entries_manager=entries_manager,
            table_show_manager=table_show_manager,
        )

    if etype == "album":
        entries_manager.clear()
        table_show_manager.clear()
        track_manager = get_tracks_func(entry)
        if len(track_manager) <= 0:
            console.print(f"[red]No tracks found for {entry.name}")
            return False

        if (
            download_album_func
            and msg.ask(
                f"\n[cyan]Download the whole album '{entry.name}'? [yellow]",
                choices=["y", "n"],
                default="n",
            ).lower()
            == "y"
        ):
            return download_album_func(entry) is not None

        tracks = select_tracks_to_download(track_manager, table_show_manager)
        if not tracks:
            return False
        for track in tracks:
            try:
                download_track_func(track)
            except Exception as e:
                console.print(f"[red]Error downloading {track.name}: {e}")
        return True

    if etype in ("song", "track"):
        try:
            download_track_func(entry)
            return True
        except Exception as e:
            console.print(f"[red]Error downloading {entry.name}: {e}")
            return False

    console.print(f"[red]Unknown media type: {entry.type}")
    return False
