# 16.10.25 - MangaWorld manga info via DOM scraping

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from httpx2 import HTTPError

from StreamingCommunity.services._base.object import Episode, Season, SeasonManager
from StreamingCommunity.utils.http_client import create_client, get_userAgent

# Variable
headers = {"user-agent": get_userAgent()}
logger = logging.getLogger(__name__)

_CHAPTER_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")


def _get_shared_client():
    return create_client(headers=headers)


def _parse_chapter_number(name: str, fallback: int) -> float:
    """Extract a numeric chapter number from a label such as 'Capitolo 1196'."""
    match = _CHAPTER_NUMBER_RE.search(name or "")
    if not match:
        return fallback
    try:
        return float(match.group(1))
    except ValueError:
        return fallback


class GetMangaInfo:
    """Scrape a MangaWorld manga page for its volumes and chapters."""

    def __init__(
        self,
        url: str | None = None,
        manga_name: str | None = None,
    ):
        self.url = url
        self.manga_name = manga_name or ""
        self.seasons_manager = SeasonManager()
        self._client = _get_shared_client()
        self._loaded = False

    def _load(self) -> bool:
        if self._loaded:
            return bool(self.seasons_manager.seasons)
        self._loaded = True

        if not self.url:
            return False

        try:
            response = self._client.get(self.url)
            response.raise_for_status()
        except HTTPError as e:
            logger.warning(f"Manga page scrape failed: {e}")
            return False

        soup = BeautifulSoup(response.text, "html.parser")
        self._parse_page(soup)
        return bool(self.seasons_manager.seasons)

    def _parse_page(self, soup: BeautifulSoup) -> None:
        # Primary structure: #chapterList -> .volume-element (one per volume)
        volume_elements = soup.select(".volume-element")

        if not volume_elements:
            # Fallback: every chapter link on the page, grouped under one volume
            season = Season(number=1, name="Volume 1")
            self._add_chapters_from_container(season, soup)
            if season.episodes.episodes:
                self.seasons_manager.add(season)
            return

        for index, element in enumerate(volume_elements, 1):
            volume_label = element.select_one(".volume")
            volume_name = (
                volume_label.get_text(" ", strip=True)
                if volume_label
                else f"Volume {index}"
            )
            volume_number = _parse_chapter_number(volume_name, index)

            season = Season(number=volume_number, name=volume_name)
            self._add_chapters_from_container(season, element)

            # Keep volumes even if empty so ordering/numbering stays intact
            self.seasons_manager.add(season)

    def _add_chapters_from_container(self, season: Season, container) -> None:
        chapter_number_fallback = 1
        for chapter in container.select(".chapter"):
            link = chapter.select_one("a.chap[href]")
            if not link:
                continue
            href = link.get("href", "")
            if not isinstance(href, str) or not href:
                continue

            name = link.get_text(" ", strip=True)
            number = _parse_chapter_number(name, chapter_number_fallback)
            chapter_number_fallback = int(number) + 1
            url = href if href.startswith("http") else urljoin(self.url or "", href)

            season.episodes.add(
                Episode(
                    id=href.rstrip("/").split("/")[-1],
                    number=number,
                    name=name or f"Capitolo {int(number)}",
                    url=url,
                )
            )

    def get_volumes(self) -> list[Season]:
        self._load()
        return self.seasons_manager.seasons

    def get_chapters_in_volume(self, volume_number) -> list[Episode]:
        self._load()
        season = self.seasons_manager.get_season_by_number(volume_number)
        if not season:
            return []
        return season.episodes.episodes

    def get_all_chapters(self) -> list[tuple[Season, Episode]]:
        self._load()
        result: list[tuple[Season, Episode]] = []
        for season in sorted(self.seasons_manager.seasons, key=lambda s: s.number or 0):
            for ep in sorted(season.episodes.episodes, key=lambda e: e.number or 0):
                result.append((season, ep))
        return result

    def close(self):
        try:
            self._client.close()
        except Exception:
            pass
