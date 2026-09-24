# Mutable state shared between the Seasons and Episodes screens so a
# multi-season batch can be walked season by season.

from __future__ import annotations

from typing import Any


class SeasonBatch:
    def __init__(
        self,
        provider: Any,
        entry: Any,
        scraper: Any,
        seasons: list[int],
        mode: str,
    ):
        self.provider = provider
        self.entry = entry
        self.scraper = scraper
        self.seasons = list(seasons)
        self.mode = mode

    def first(self) -> int | None:
        if not self.seasons:
            return None
        return self.seasons[0]

    def next_after(self, season_number: int) -> int | None:
        try:
            idx = self.seasons.index(int(season_number))
        except ValueError:
            return None
        if idx + 1 < len(self.seasons):
            return self.seasons[idx + 1]
        return None