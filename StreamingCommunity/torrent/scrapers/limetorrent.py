# 2026

import logging
import re
from typing import List, Optional
from html import unescape

from bs4 import BeautifulSoup, Tag

from StreamingCommunity.torrent.scrapers.base import BaseScraper
from StreamingCommunity.torrent.title_parser import TorrentResult
from StreamingCommunity.utils.http_client import create_client_curl

log = logging.getLogger(__name__)

_CATEGORY_MAP = {
    "movies": "movies",
    "tv": "tv",
    "anime": "anime",
    "music": "music",
    "games": "games",
    "applications": "apps",
    "apps": "apps",
    "other": "other",
}


class LimeTorrentScraper(BaseScraper):
    """LimeTorrents scraper — curl_cffi Cloudflare bypass, HTML parsing. Base URL from Conf/domains.json."""

    name = "limetorrent"

    def __init__(self, config_manager):
        super().__init__(config_manager)
        self.BASE_URL = config_manager.domain.get("limetorrent", "full_url", default="https://www.limetorrents.pro")
        self.MIRRORS = config_manager.domain.get(
            "limetorrent", "mirrors",
            default=["https://www.limetorrents.pro", "https://limetorrents.cc"]
        )

    def _fetch_page(self, url: str) -> Optional[str]:
        try:
            client = create_client_curl(impersonate=self._get_impersonate())
            resp = client.get(url)
            return resp.text
        except Exception as e:
            log.warning("LimeTorrents request failed: %s", e)
            return None

    def _try_mirrors(self, path: str) -> Optional[str]:
        for base in self.MIRRORS:
            url = f"{base}{path}"
            html = self._fetch_page(url)
            if html and "table2" in html:
                self._active_base = base
                return html
        log.warning("LimeTorrents: all mirrors failed for %s", path)
        return None

    @staticmethod
    def _extract_category(added_text: str) -> str:
        m = re.search(r"in\s+(.+?)$", added_text.strip())
        if m:
            raw = m.group(1).strip().rstrip(".").lower()
            return _CATEGORY_MAP.get(raw, raw)
        return "other"

    def _parse_search_row(self, row: Tag) -> Optional[tuple]:
        tds = row.select("td")
        if len(tds) < 5:
            return None

        td_name = tds[0]
        td_added = tds[1]
        td_size = tds[2]
        td_seed = tds[3]
        td_leech = tds[4]

        tt_div = td_name.select_one("div.tt-name")
        if not tt_div:
            return None

        links = tt_div.select("a")
        title = ""
        detail_path = ""
        torrent_url = ""

        for a in links:
            href = str(a.get("href", ""))
            if "csprite_dl14" in " ".join(a.get("class", [])):
                torrent_url = href
            elif href.startswith("/") and "-torrent-" in href:
                title = a.get_text(strip=True)
                detail_path = href

        if not title:
            return None

        added_text = td_added.get_text(strip=True)
        category = self._extract_category(added_text)

        size_bytes = self._parse_size(td_size.get_text(strip=True))
        seeders = self._safe_int(td_seed.get_text(strip=True))
        leechers = self._safe_int(td_leech.get_text(strip=True))
        quality = self._extract_quality(title)

        return TorrentResult(
            title=title,
            quality=quality,
            size_bytes=size_bytes,
            seeders=seeders,
            leechers=leechers,
            source="limetorrent",
            magnet_url="",
            torrent_url=torrent_url,
            category=category,
            year=self._extract_year(title),
            tmdb_id=None,
        ), detail_path

    def _parse_search_page(self, html: str, category: str = "") -> List[tuple]:
        soup = BeautifulSoup(html, "html.parser")
        table2 = soup.select_one("table.table2")
        if not table2:
            return []

        results: List[tuple] = []
        for row in table2.select("tr")[1:]:
            try:
                pair = self._parse_search_row(row)
                if pair:
                    results.append(pair)
            except Exception as e:
                log.debug("LimeTorrents row parse error: %s", e)
                continue

        return results

    def get_magnet(self, detail_url: str) -> Optional[str]:
        if detail_url.startswith("/"):
            base = getattr(self, "_active_base", self.MIRRORS[0])
            detail_url = f"{base}{detail_url}"

        html = self._fetch_page(detail_url)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")

        magnet_tag = soup.select_one('a[href^="magnet:"]')
        if magnet_tag:
            return unescape(str(magnet_tag.get("href", "")))

        hash_b = next(
            (b for b in soup.find_all("b") if "Torrent Hash" in b.get_text()),
            None,
        )
        if hash_b:
            td = hash_b.find_next("td")
            if td:
                info_hash = td.get_text(strip=True).upper()
                if re.match(r"^[A-F0-9]{40}$", info_hash):
                    return self._build_magnet(info_hash)

        return None

    def _fetch_magnets_batch(self, results: List[tuple], max_fetch: int = 5) -> None:
        fetched = 0
        for i, (result, detail_path) in enumerate(results):
            if result.magnet_url or fetched >= max_fetch:
                continue
            if not detail_path:
                continue
            magnet = self.get_magnet(detail_path)
            if magnet:
                results[i] = (
                    TorrentResult(
                        title=result.title,
                        quality=result.quality,
                        size_bytes=result.size_bytes,
                        seeders=result.seeders,
                        leechers=result.leechers,
                        source=result.source,
                        magnet_url=magnet,
                        torrent_url=result.torrent_url,
                        category=result.category,
                        year=result.year,
                        tmdb_id=result.tmdb_id,
                    ),
                    detail_path,
                )
                fetched += 1

    def search(
        self,
        query: str,
        page: int = 1,
        limit: int = 20,
        category: str = "",
        **kwargs,
    ) -> List[TorrentResult]:
        cat_part = category or "all"
        path = f"/search/{cat_part}/{query}/date/{page}/"

        html = self._try_mirrors(path)
        if not html:
            return []

        parsed = self._parse_search_page(html, category)
        has_magnets = any(r.magnet_url for r, _ in parsed)

        if not has_magnets:
            self._fetch_magnets_batch(parsed, max_fetch=limit)

        return [r for r, _ in parsed[:limit]]

    def search_by_category(
        self,
        category: str,
        page: int = 1,
        limit: int = 20,
    ) -> List[TorrentResult]:
        browse_map = {
            "movies": "Movies",
            "tv": "TV-shows",
            "anime": "Anime",
            "music": "Music",
            "games": "Games",
            "apps": "Applications",
            "other": "Other",
        }
        browse_name = browse_map.get(category.lower(), category)
        path = f"/browse-torrents/{browse_name}/"

        html = self._try_mirrors(path)
        if not html:
            return []

        parsed = self._parse_search_page(html, category)
        has_magnets = any(r.magnet_url for r, _ in parsed)

        if not has_magnets:
            self._fetch_magnets_batch(parsed, max_fetch=limit)

        return [r for r, _ in parsed[:limit]]
