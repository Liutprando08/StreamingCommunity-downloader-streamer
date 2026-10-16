# Adapters for the single-video services (YouTube, MostraGuarda, Ipersphera).
#
# A search hit is one indivisible download here -- there is no season/episode
# metadata to walk -- so these providers use the "atomic" flow: search ->
# detail -> queue, exactly like torrent. ``is_series`` is always False, which
# is what makes the detail screen skip the seasons screen and push the queue
# with a single "film" item straight away.

from __future__ import annotations

import importlib
from typing import Any

from .base import service_search_lock


class FilmProviderBase:
    flow = "atomic"
    category = "Film"
    # These are generic single-video services rather than film/serie catalogs,
    # so the home screen groups them under the "Altro" sector.
    sector = "other"
    supports_streaming = False
    supports_seasons = False

    # Set by subclasses: the folder under StreamingCommunity/services/.
    module_name: str = ""

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

    def search(self, query: str) -> list[Any]:
        service = self._module()
        with service_search_lock(self.module_name):
            service.entries_manager.clear()
            service.title_search(query)
            # Keep the service's own ordering (YouTube's is relevance-ranked).
            return list(service.entries_manager.media_list)

    def result_columns(self) -> tuple[tuple[str, str], ...]:
        return (
            ("Nome", "name"),
            ("Tipo", "type"),
        )

    def is_series(self, entry: Any) -> bool:
        # Nothing to walk: the picked entry is the whole download.
        return False

    def download_film(self, entry: Any) -> Any:
        return self._downloader().download_film(entry)

    def stream_film(self, entry: Any) -> None:
        return None

    def download_episode(self, *args: Any) -> None:
        return None

    def stream_episode(self, *args: Any) -> None:
        return None


class YouTubeProvider(FilmProviderBase):
    name = "YouTube"
    category = "Film_Serie"
    alias = "youtube"
    module_name = "youtube"

    def result_columns(self) -> tuple[tuple[str, str], ...]:
        # ``size`` carries the duration and ``desc`` the channel name.
        return (
            ("Nome", "name"),
            ("Tipo", "type"),
            ("Durata", "size"),
            ("Canale", "desc"),
        )


class MostraGuardaProvider(FilmProviderBase):
    name = "MostraGuarda"
    category = "Film"
    alias = "mostraguarda"
    module_name = "mostraguarda"


class IperspheraProvider(FilmProviderBase):
    name = "Ipersphera"
    category = "Film_Serie"
    alias = "ipersphera"
    module_name = "ipersphera"