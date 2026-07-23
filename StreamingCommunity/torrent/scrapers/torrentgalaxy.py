# 2026

import logging
import re
from typing import List, Optional
from html import unescape
from bs4 import BeautifulSoup, Tag
from StreamingCommunity.torrent.scrapers.base import BaseScraper
from StreamingCommunity.torrent.title_parser import TorrentResult
from StreamingCommunity.utils.http_client import create_client_curl
from typing import Tuple

log = logging.getLogger(__name__)

_QUALITY_RE = re.compile(
    r"(2160p|1080p|720p|480p|4K|WEB(?:-?DL|Rip)?|HDRip|BluRay|BRRip|DVDRip|HDTV|TELESYNC|CAM|\bTS\b|\bTC\b)",
    re.IGNORECASE,
)


class TorrentGalaxyScraper(BaseScraper):
    """TorrentGalaxy scraper — Cloudflare bypassed via curl_cffi impersonation, HTML parsing. Base URL from Conf/domains.json."""

    name = "torrentgalaxy"

    def __init__(self, config_manager):
        super().__init__(config_manager)
        self.BASE_URL = config_manager.domain.get("torrentgalaxy", "full_url", default="https://torrentgalaxy.is")
        self.MIRRORS = config_manager.domain.get(
            "torrentgalaxy", "mirrors",
            default=["https://torrentgalaxy.is", "https://torrentgalaxy.cc"]
        )
        self.torrent_config = None
        try:
            from StreamingCommunity.torrent.config import TorrentConfig

            self.torrent_config = TorrentConfig(config_manager)
        except Exception:
            pass

    def _get_impersonate(self) -> str:
        if self.torrent_config:
            return self.torrent_config.scrape_impersonate
        return "chrome"

    def _parse_size(self, size_str: str) -> int:
        normalized = size_str.replace("\xa0", " ").replace("\u2009", " ")
        parts = normalized.strip().split()
        if len(parts) < 2:
            return 0
        try:
            value = float(parts[0])
            unit = parts[1].upper()
            multipliers = {
                "B": 1,
                "KB": 1024,
                "MB": 1024**2,
                "GB": 1024**3,
                "TB": 1024**4,
            }
            return int(value * multipliers.get(unit, 1))
        except (ValueError, IndexError):
            return 0

    def _extract_quality(self, title: str) -> str:
        matches = _QUALITY_RE.findall(title)
        return " ".join(dict.fromkeys(m.upper() for m in matches))

    def _parse_magnet_hash(self, magnet_url: str) -> str:
        m = re.search(r"urn:btih:([a-fA-F0-9]{40}|[a-zA-Z2-7]{32})", magnet_url)
        return m.group(1) if m else ""

    @staticmethod
    def _safe_int(text: str) -> int:
        try:
            return int(text.replace(",", ""))
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _extract_year(title: str) -> Optional[int]:
        m = re.search(r"[\(\[\s]?((?:19|20)\d{2})[\)\]\s]?", title)
        return int(m.group(1)) if m else None

    def _parse_rows(self, html: str, category: str = "") -> List[TorrentResult]:
        soup = BeautifulSoup(html, "html.parser")
        results: List[TorrentResult] = []

        rows = soup.select("div.tgxtablerow")
        for row in rows:
            try:
                pair = self._parse_single_row(row, category)
                if pair:
                    result, _post_path = pair
                    results.append(result)
            except Exception as e:
                log.debug("TorrentGalaxy row parse error: %s", e)
                continue

        return results

    def _parse_single_row(
        self, row: Tag, category: str
    ) -> Optional[Tuple[TorrentResult, str]]:
        title_cell = row.select_one("div.tgxtablecell.clickable-row")
        if not title_cell:
            return None

        title_tag = title_cell.select_one("a[href]")
        if not title_tag:
            return None

        title = str(title_tag.get("title", "")).strip()
        if not title:
            b_tag = title_tag.select_one("b")
            title = b_tag.get_text(strip=True) if b_tag else ""
        if not title:
            return None

        magnet_url = ""
        torrent_url = ""
        for a_tag in row.select("a[href]"):
            href = str(a_tag.get("href", ""))
            if href.startswith("magnet:"):
                magnet_url = unescape(href)
            elif "itorrents.org/torrent/" in href:
                torrent_url = href
        size_bytes = 0
        for span in row.select("span.badge.badge-secondary"):
            text = span.get_text(strip=True)
            if re.search(r"\d+[\.,]?\d*\s*(B|KB|MB|GB|TB)", text, re.IGNORECASE):
                size_bytes = self._parse_size(text)
                break

        seeders = 0
        leechers = 0
        sl_span = row.select_one('span[title*="Seeders"]')
        if sl_span:
            green = sl_span.select_one('font[color="green"] b')
            red = sl_span.select_one('font[color="#ff0000"] b')
            if green:
                seeders = self._safe_int(green.get_text(strip=True))
            if red:
                leechers = self._safe_int(red.get_text(strip=True))

        quality = self._extract_quality(title)

        post_path = str(title_cell.get("data-href", ""))
        if post_path and post_path.startswith("/"):
            post_path = post_path

        row_category = category
        if not row_category:
            cat_link = row.select_one(
                "div.tgxtablecell.shrink a[href*='/get-posts/category:']"
            )
            if cat_link:
                cat_href = str(cat_link.get("href", ""))
                cat_match = re.search(r"/get-posts/category:(\w+)", cat_href)
                if cat_match:
                    row_category = cat_match.group(1).lower()

        return TorrentResult(
            title=title,
            quality=quality,
            size_bytes=size_bytes,
            seeders=seeders,
            leechers=leechers,
            source="torrentgalaxy",
            magnet_url=magnet_url,
            torrent_url=torrent_url,
            category=row_category or "movie",
            year=self._extract_year(title),
            tmdb_id=None,
        ), post_path

    def _fetch_page(self, url: str) -> Optional[str]:
        try:
            client = create_client_curl(impersonate=self._get_impersonate())
            resp = client.get(url)
            return resp.text
        except Exception as e:
            log.warning("TorrentGalaxy request failed: %s", e)
            return None

    def _try_mirrors(self, path: str) -> Optional[str]:
        for base in self.MIRRORS:
            url = f"{base}{path}"
            html = self._fetch_page(url)
            if html and "tgxtablerow" in html:
                self._active_base = base
                return html
        log.warning("TorrentGalaxy: all mirrors failed for %s", path)
        return None

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
            return unescape(str(magnet_tag["href"]))

        torrent_tag = soup.select_one('a[href*="itorrents.org/torrent/"]')
        if torrent_tag:
            href = str(torrent_tag["href"])
            m = re.search(r"/torrent/([A-Fa-f0-9]{40})", href)
            if m:
                info_hash = m.group(1).upper()
                title_match = re.search(r"\?title=(.+)$", href)
                dn = title_match.group(1) if title_match else ""
                return self._build_magnet(info_hash, dn)

        return None

    @staticmethod
    def _build_magnet(info_hash: str, dn: str = "") -> str:
        from urllib.parse import quote_plus

        trackers = [
            "udp://open.stealth.si:80/announce",
            "udp://tracker.opentrackr.org:1337/announce",
            "udp://open.demonii.com:1337/announce",
            "udp://tracker.torrent.eu.org:451/announce",
        ]
        parts = [f"magnet:?xt=urn:btih:{info_hash}"]
        if dn:
            parts.append(f"dn={quote_plus(dn)}")
        for tr in trackers:
            parts.append(f"tr={quote_plus(tr)}")
        return "&".join(parts)

    def _fetch_magnets_batch(
        self, results: List[TorrentResult], post_paths: List[str], max_fetch: int = 10
    ) -> None:
        fetched = 0
        for i, (result, path) in enumerate(zip(results, post_paths)):
            if result.magnet_url or fetched >= max_fetch:
                continue
            if not path:
                continue
            magnet = self.get_magnet(path)
            if magnet:
                results[i] = TorrentResult(
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
        path = f"/get-posts/keywords:{query}"
        params = []
        if page > 1:
            params.append(f"page={page}")
        if params:
            path += "?" + "&".join(params)

        html = self._try_mirrors(path)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("div.tgxtablerow")
        parsed: List[TorrentResult] = []
        post_paths: List[str] = []

        for row in rows:
            try:
                pair = self._parse_single_row(row, category)
                if pair:
                    result, post_path = pair
                    parsed.append(result)
                    post_paths.append(post_path)
            except Exception as e:
                log.debug("TorrentGalaxy row parse error: %s", e)
                continue

        has_inline_magnets = any(r.magnet_url for r in parsed)
        if not has_inline_magnets:
            self._fetch_magnets_batch(parsed, post_paths, max_fetch=limit)

        return parsed[:limit] if limit else parsed

    def search_by_category(
        self,
        category: str,
        page: int = 1,
        limit: int = 20,
    ) -> List[TorrentResult]:
        path = f"/get-posts/category:{category}"
        if page > 1:
            path += f"?page={page}"

        html = self._try_mirrors(path)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("div.tgxtablerow")
        parsed: List[TorrentResult] = []
        post_paths: List[str] = []

        for row in rows:
            try:
                pair = self._parse_single_row(row, category)
                if pair:
                    result, post_path = pair
                    parsed.append(result)
                    post_paths.append(post_path)
            except Exception as e:
                log.debug("TorrentGalaxy row parse error: %s", e)
                continue

        has_inline_magnets = any(r.magnet_url for r in parsed)
        if not has_inline_magnets:
            self._fetch_magnets_batch(parsed, post_paths, max_fetch=limit)

        return parsed[:limit] if limit else parsed
