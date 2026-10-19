# Music providers for the TUI (musicmp3, goldenmp3, monochrome).
#
# All music services share the same shape -- search by mode (song / album /
# artist), then drill down artist -> album -> tracks -- so a single
# ``MusicProvider`` class drives them and each spec only declares which service
# module it maps to and which modes that module supports.

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from .base import service_search_lock

DEFAULT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("Nome", "name"),
    ("Tipo", "type"),
    ("Artista", "artist"),
    ("Album", "album"),
)

_DEFAULT_MODES: tuple[str, ...] = ("Song", "Album", "Artist")


@dataclass(frozen=True)
class MusicSpec:
    """Everything that varies between two music services."""

    name: str
    alias: str
    module: str
    search_modes: tuple[str, ...] = _DEFAULT_MODES
    columns: tuple[tuple[str, str], ...] = DEFAULT_COLUMNS


class MusicProvider:
    """One music service, configured by its :class:`MusicSpec`."""

    flow = "music"
    category = "Music"
    supports_streaming = False
    supports_seasons = False
    # Home tab grouping comes from the category ("Music" -> music tab).
    sector: str | None = None

    def __init__(self, spec: MusicSpec) -> None:
        self._spec = spec
        self._service: Any = None

        self.name = spec.name
        self.alias = spec.alias

    # ── lazy service access ───────────────────────────────────────────────
    def _module(self):
        """Lazy import so TUI startup stays light and CLI stays untouched."""
        if self._service is None:
            self._service = importlib.import_module(
                f"StreamingCommunity.services.{self._spec.module}"
            )
        return self._service

    def _downloader(self):
        return importlib.import_module(
            f"StreamingCommunity.services.{self._spec.module}.downloader"
        )

    # ── protocol ──────────────────────────────────────────────────────────
    def search_modes(self) -> tuple[str, ...]:
        return self._spec.search_modes

    def result_columns(self) -> tuple[tuple[str, str], ...]:
        return self._spec.columns

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

        with service_search_lock(self._spec.module):
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


# ── the music services ─────────────────────────────────────────────────────
MUSIC_SPECS: dict[str, MusicSpec] = {
    spec.alias: spec
    for spec in (
        MusicSpec(
            name="Musicmp3",
            alias="musicmp3",
            module="musicmp3",
        ),
        MusicSpec(
            name="Goldenmp3",
            alias="goldenmp3",
            module="goldenmp3",
            # goldenmp3 only exposes a reliable album search, so Song/Artist are
            # not offered; this mirrors ``base_music_search(modes=("Album",))``.
            search_modes=("Album",),
        ),
        MusicSpec(
            name="Monochrome",
            alias="monochrome",
            module="monochrome",
        ),
    )
}
