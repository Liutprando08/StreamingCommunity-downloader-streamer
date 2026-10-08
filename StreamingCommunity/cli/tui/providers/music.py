# Adapters for the music services (musicmp3, goldenmp3).
#
# Both services share the same shape -- search by mode (song / album / artist),
# then drill down artist -> album -> tracks -- so a single base class drives
# them and the concrete providers only declare which service module they map to
# and which modes that module supports.

from __future__ import annotations

import importlib
from typing import Any


class MusicProviderBase:
    flow = "music"
    category = "Music"
    supports_streaming = False
    supports_seasons = False

    # Set by subclasses: the folder under StreamingCommunity/services/.
    module_name: str = ""
    _SEARCH_MODES: tuple[str, ...] = ("Song", "Album", "Artist")

    def __init__(self) -> None:
        self._service: Any = None

    def _module(self):
        """Lazy import so TUI startup stays light and CLI stays untouched."""
        if self._service is None:
            self._service = importlib.import_module(
                f"StreamingCommunity.services.{self.module_name}"
            )
        return self._service

    def _downloader(self):
        return importlib.import_module(
            f"StreamingCommunity.services.{self.module_name}.downloader"
        )

    # ── protocol ─────────────────────────────────────────────────────────
    def search_modes(self) -> tuple[str, ...]:
        return self._SEARCH_MODES

    def result_columns(self) -> tuple[tuple[str, str], ...]:
        return (
            ("Nome", "name"),
            ("Tipo", "type"),
            ("Artista", "artist"),
            ("Album", "album"),
        )

    def search(self, query: str, mode: str) -> list[Any]:
        service = self._module()
        # The service module keeps its own EntriesManager and clears it on each
        # of the title_search_* calls, so pick the function from the mode.
        title_search = {
            "Song": service.title_search_song,
            "Album": service.title_search_album,
            "Artist": service.title_search_artist,
        }.get(mode)

        if title_search is None:
            return []

        title_search(query)
        service.entries_manager.sort_by_fuzzy_score(query)
        return list(service.entries_manager.media_list)

    def albums(self, entry: Any) -> list[Any]:
        manager = self._module().get_albums(entry)
        return list(getattr(manager, "media_list", []) or [])

    def tracks(self, entry: Any) -> list[Any]:
        manager = self._module().get_tracks(entry)
        return list(getattr(manager, "media_list", []) or [])

    def drilldown(self, entry: Any) -> tuple[str, list[Any]] | None:
        """Route a picked search result to the next level, if any."""
        media_type = str(getattr(entry, "type", "") or "").lower()

        if media_type == "artist":
            return "albums", self.albums(entry)
        if media_type == "album":
            return "tracks", self.tracks(entry)

        # Songs are downloaded straight away, no intermediate listing.
        return None

    def download_track(self, entry: Any) -> Any:
        return self._downloader().download_track(entry)

    def download_album(self, entry: Any) -> Any:
        return self._downloader().download_album(entry, self._module().get_tracks)


class Musicmp3Provider(MusicProviderBase):
    name = "Musicmp3"
    alias = "Music"
    module_name = "musicmp3"
    _SEARCH_MODES = ("Song", "Album", "Artist")


class Goldenmp3Provider(MusicProviderBase):
    name = "Goldenmp3"
    alias = "Music"
    module_name = "goldenmp3"
    # goldenmp3 only exposes a reliable album search, so Song/Artist are not
    # offered; this mirrors ``base_music_search(modes=("Album",))``.
    _SEARCH_MODES = ("Album",)

