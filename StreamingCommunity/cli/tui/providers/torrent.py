# Torrent adapter for the TUI.
#
# A torrent result is an opaque magnet link: there is no season/episode
# metadata to walk, and ``services.torrent.downloader`` downloads whatever the
# user picked in one shot. So this provider uses the atomic flow -- search ->
# detail -> queue -- and only reuses ``download_film`` as the queue entry point,
# which routes to the movie or series folder based on the entry type.

from __future__ import annotations

from typing import Any


class TorrentProvider:
    name = "Torrent"
    category = "Film_Serie"
    alias = "torrent"

    flow = "atomic"
    supports_streaming = False
    supports_seasons = False

    _SERIES_TYPES = {"tv"}

    def __init__(self) -> None:
        self._service: Any = None

    def _module(self):
        """Lazy import so TUI startup stays light and CLI stays untouched."""
        if self._service is None:
            import StreamingCommunity.services.torrent as service

            self._service = service
        return self._service

    def _downloader(self):
        from StreamingCommunity.services.torrent import downloader

        return downloader

    def search(self, query: str) -> list[Any]:
        # title_search() clears the manager and repopulates the module-level
        # ``_torrent_results`` map keyed by entry.id, which download_film
        # re-reads. Do not sort: the service already orders by seeders.
        service = self._module()
        service.title_search(query)
        return list(service.entries_manager.media_list)

    def result_columns(self) -> tuple[tuple[str, str], ...]:
        # Seeders / size / quality are what actually decides a torrent pick,
        # and the site-specific entries expose them.
        return (
            ("Nome", "name"),
            ("Tipo", "type"),
            ("Anno", "year"),
            ("Qualità", "quality"),
            ("Dim.", "size"),
            ("Seed", "seeders"),
            ("Fonte", "source"),
        )

    def is_series(self, entry: Any) -> bool:
        return str(getattr(entry, "type", "") or "").lower() in self._SERIES_TYPES

    def download_film(self, entry: Any) -> Any:
        downloader = self._downloader()
        # prompt_dub=False: the Italian audio dub flow asks questions on stdin,
        # which would block this TUI worker thread forever.
        if self.is_series(entry):
            return downloader.download_series(entry, prompt_dub=False)
        return downloader.download_film(entry, prompt_dub=False)