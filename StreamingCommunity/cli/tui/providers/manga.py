# MangaWorld adapter for the TUI. Wraps the existing ``services/mangaworld``
# search/scraper/downloader instead of re-implementing the MangaWorld plumbing.
#
# MangaWorld has no streaming path: search hits are manga, each "season" is a
# volume and each "episode" is a chapter that the downloader packages into a
# ``.cbz`` archive. ``supports_streaming`` is therefore False and the detail
# screen hides the streaming button.

from __future__ import annotations

import importlib
from typing import Any


def _chapter_sort_key(episode: Any) -> tuple[int, float]:
    """Sort chapters by number, keeping unparseable ones last and stable."""
    try:
        return (0, float(getattr(episode, "number", None)))
    except (TypeError, ValueError):
        return (1, 0.0)


class MangaWorldProvider:
    name = "MangaWorld"
    category = "Manga"
    alias = "mangaworld"
    # Manga is neither a film nor music, so the home screen groups it under
    # the "Altro" sector.
    sector = "other"

    flow = "episode"
    supports_streaming = False
    supports_seasons = True

    # Cosmetic overrides so the preview/detail cards say "Manga" (instead of
    # the default "Serie") for this provider.
    series_icon = "📚"
    series_label = "Manga"

    def __init__(self) -> None:
        self._service: Any = None

    def _module(self):
        """Lazy import so TUI startup stays light and CLI stays untouched."""
        if self._service is None:
            self._service = importlib.import_module(
                "StreamingCommunity.services.mangaworld"
            )
        return self._service

    def _downloader(self):
        return importlib.import_module(
            "StreamingCommunity.services.mangaworld.downloader"
        )

    def search(self, query: str) -> list[Any]:
        service = self._module()
        service.entries_manager.clear()
        service.title_search(query)
        service.entries_manager.sort_by_fuzzy_score(query)
        return list(service.entries_manager.media_list)

    def result_columns(self) -> tuple[tuple[str, str], ...]:
        return (
            ("Nome", "name"),
            ("Tipo", "type"),
            ("Anno", "year"),
        )

    def is_series(self, entry: Any) -> bool:
        # A manga is always walked through volumes (seasons) and chapters.
        return True

    def entry_description(self, entry: Any) -> str | None:
        # The search payload only carries a stub; fetch the real synopsis.
        try:
            return self._module().get_full_description(entry)
        except Exception:
            return None

    def new_series_scraper(self, entry: Any) -> Any:
        from StreamingCommunity.services.mangaworld.scrapper import GetMangaInfo

        return GetMangaInfo(
            url=getattr(entry, "url", None),
            manga_name=getattr(entry, "name", None),
        )

    def seasons(self, scraper: Any) -> list[Any]:
        # A "season" is a volume.
        return list(scraper.get_volumes())

    def episodes(self, scraper: Any, season_number: int) -> list[Any]:
        # A "season" is a volume; a chapter is an "episode". MangaWorld lists
        # chapters newest-first, but the TUI reads top-down, so sort them into
        # ascending chapter order.
        return sorted(
            scraper.get_chapters_in_volume(season_number), key=_chapter_sort_key
        )

    def download_film(self, entry: Any) -> Any:
        # Fallback for the (unused) atomic path: download the whole collection.
        return self._downloader().download_manga(entry)

    def stream_film(self, entry: Any) -> None:
        # Never offered: manga has no stream path.
        return None

    def download_episode(
        self, obj_episode: Any, season: int, episode: int, scraper: Any
    ) -> Any:
        # ``scraper`` is the GetMangaInfo built by ``new_series_scraper`` and
        # carries the manga name; ``season`` is the volume number.
        volume = None
        try:
            volume = scraper.seasons_manager.get_season_by_number(season)
        except Exception:
            volume = None
        volume_name = getattr(volume, "name", None) if volume else None
        manga_name = getattr(scraper, "manga_name", None) or "Manga"
        return self._downloader().download_chapter(
            obj_episode, manga_name, volume_name
        )

    def stream_episode(
        self, obj_episode: Any, season: int, episode: int, scraper: Any
    ) -> None:
        return None
