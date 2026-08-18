from __future__ import annotations

import logging
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from rich.console import Console

from StreamingCommunity.utils import config_manager
from StreamingCommunity.utils.tmdb_client import tmdb

console = Console()

KODI_NFO_FILES = config_manager.config.get_bool("PROCESS", "kodi_nfo", default=False)
logger = logging.getLogger(__name__)


def _extract_slug_from_path(file_path: str, media_type: str) -> str:
    """Extract a slug from the output path to use for TMDB search."""
    p = Path(file_path)
    if media_type and media_type.lower() in ("tv", "series", "show"):
        parent = p.parent.name
        if parent and parent not in ("Movie", "Serie", "Anime"):
            return parent
    name = p.stem
    name = re.sub(r"\s*S\d{2}E\d{2}.*", "", name)
    name = re.sub(r"[_\s]+", " ", name).strip()
    return name if name else p.parent.name


def _slugify(text: str) -> str:
    """Simple slugify for filename-based matching."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text.strip("-")


def _ensure_xml_declaration(root: ET.Element) -> str:
    """Return XML string with proper declaration."""
    rough_string = ET.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + rough_string


def _safe_text(value) -> str:
    """Convert a value to string or return empty string."""
    if value is None:
        return ""
    return str(value)


def _build_movie_nfo(
    details: dict,
    output_dir: str,
    poster_url: str | None = None,
    fanart_url: str | None = None,
) -> str:
    """Build movie NFO XML string."""
    movie = ET.Element("movie")

    title = ET.SubElement(movie, "title")
    title.text = _safe_text(details.get("title", ""))

    original = ET.SubElement(movie, "originaltitle")
    original.text = _safe_text(details.get("original_title", ""))

    if details.get("year"):
        year = ET.SubElement(movie, "year")
        year.text = str(details["year"])

    if details.get("rating") is not None:
        rating = ET.SubElement(movie, "rating")
        rating.text = str(round(details["rating"], 1))

    if details.get("votes") is not None:
        votes = ET.SubElement(movie, "votes")
        votes.text = str(details["votes"])

    if details.get("plot"):
        plot = ET.SubElement(movie, "plot")
        plot.text = details["plot"]

    if details.get("mpaa"):
        mpaa = ET.SubElement(movie, "mpaa")
        mpaa.text = details["mpaa"]

    if details.get("imdb_id"):
        uid_imdb = ET.SubElement(movie, "uniqueid")
        uid_imdb.set("type", "imdb")
        uid_imdb.set("default", "false")
        uid_imdb.text = details["imdb_id"]

    if details.get("director"):
        director = ET.SubElement(movie, "director")
        director.text = details["director"]

    for genre_name in details.get("genres", []):
        genre = ET.SubElement(movie, "genre")
        genre.text = genre_name

    for actor in details.get("cast", []):
        actor_el = ET.SubElement(movie, "actor")
        name_el = ET.SubElement(actor_el, "name")
        name_el.text = _safe_text(actor.get("name"))
        role_el = ET.SubElement(actor_el, "role")
        role_el.text = _safe_text(actor.get("role"))

    if poster_url:
        thumb_el = ET.SubElement(movie, "thumb")
        thumb_el.set("aspect", "poster")
        thumb_el.text = "poster.jpg"

    if fanart_url:
        fanart_el = ET.SubElement(movie, "fanart")
        thumb_el = ET.SubElement(fanart_el, "thumb")
        thumb_el.text = "fanart.jpg"

    return _ensure_xml_declaration(movie)


def _build_tvshow_nfo(details: dict) -> str:
    """Build TV show NFO XML string."""
    tvshow = ET.Element("tvshow")

    title = ET.SubElement(tvshow, "title")
    title.text = _safe_text(details.get("title", ""))

    original = ET.SubElement(tvshow, "originaltitle")
    original.text = _safe_text(details.get("original_title", ""))

    if details.get("year"):
        year = ET.SubElement(tvshow, "year")
        year.text = str(details["year"])

    if details.get("rating") is not None:
        rating = ET.SubElement(tvshow, "rating")
        rating.text = str(round(details["rating"], 1))

    if details.get("votes") is not None:
        votes = ET.SubElement(tvshow, "votes")
        votes.text = str(details["votes"])

    if details.get("plot"):
        plot = ET.SubElement(tvshow, "plot")
        plot.text = details["plot"]

    if details.get("mpaa"):
        mpaa = ET.SubElement(tvshow, "mpaa")
        mpaa.text = details["mpaa"]

    if details.get("imdb_id"):
        uid_imdb = ET.SubElement(tvshow, "uniqueid")
        uid_imdb.set("type", "imdb")
        uid_imdb.set("default", "false")
        uid_imdb.text = details["imdb_id"]

    for genre_name in details.get("genres", []):
        genre = ET.SubElement(tvshow, "genre")
        genre.text = genre_name

    for actor in details.get("cast", []):
        actor_el = ET.SubElement(tvshow, "actor")
        name_el = ET.SubElement(actor_el, "name")
        name_el.text = _safe_text(actor.get("name"))
        role_el = ET.SubElement(actor_el, "role")
        role_el.text = _safe_text(actor.get("role"))

    return _ensure_xml_declaration(tvshow)


def _build_episode_nfo(
    details: dict, season_num: int | None = None, episode_num: int | None = None
) -> str:
    """Build episode details NFO XML string."""
    ep = ET.Element("episodedetails")

    title = ET.SubElement(ep, "title")
    title.text = _safe_text(details.get("title", ""))

    if details.get("plot"):
        plot = ET.SubElement(ep, "plot")
        plot.text = details["plot"]

    if season_num is not None:
        season = ET.SubElement(ep, "season")
        season.text = str(season_num)

    if episode_num is not None:
        episode = ET.SubElement(ep, "episode")
        episode.text = str(episode_num)

    if details.get("rating") is not None:
        rating = ET.SubElement(ep, "rating")
        rating.text = str(round(details["rating"], 1))

    return _ensure_xml_declaration(ep)


class KodiNFOGenerator:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.output_dir = self.file_path.parent

    def _resolve_tmdb(self, slug: str, media_type: str):
        """Resolve a slug to TMDB type and ID."""
        tmdb_type = (
            "movie" if media_type and media_type.lower() in ("film", "movie") else "tv"
        )
        result = tmdb.get_type_and_id_by_slug_year(slug, media_type=tmdb_type)
        if result and result.get("id"):
            return result
        return None

    def generate_for_movie(self, slug: str | None = None):
        """Generate movie NFO + images."""
        if slug is None:
            slug = _extract_slug_from_path(str(self.file_path), "movie")

        tmdb_info = self._resolve_tmdb(slug, "movie")
        if not tmdb_info or not tmdb_info.get("id"):
            logger.warning(f"[KodiNFO] Could not resolve TMDB ID for movie: {slug}")
            return False

        details = tmdb.get_full_details("movie", tmdb_info["id"])
        if not details:
            logger.warning(
                f"[KodiNFO] Could not fetch details for TMDB ID {tmdb_info['id']}"
            )
            return False

        poster_url = None
        fanart_url = None
        images = tmdb.get_images("movie", tmdb_info["id"])

        if images.get("posters"):
            poster_path = os.path.join(self.output_dir, "poster.jpg")
            if tmdb.download_image(images["posters"][0], poster_path):
                poster_url = images["posters"][0]
                logger.info(f"[KodiNFO] Downloaded poster for {slug}")

        if images.get("backdrops"):
            fanart_path = os.path.join(self.output_dir, "fanart.jpg")
            if tmdb.download_image(images["backdrops"][0], fanart_path):
                fanart_url = images["backdrops"][0]
                logger.info(f"[KodiNFO] Downloaded fanart for {slug}")

        nfo_content = _build_movie_nfo(
            details, str(self.output_dir), poster_url, fanart_url
        )
        nfo_path = os.path.join(self.output_dir, "movie.nfo")
        with open(nfo_path, "w", encoding="utf-8") as f:
            f.write(nfo_content)
        logger.info(f"[KodiNFO] Created movie.nfo for {slug}")
        return True

    def generate_for_tvshow(self, slug: str | None = None):
        """Generate tvshow.nfo + images in the parent directory."""
        if slug is None:
            slug = _extract_slug_from_path(str(self.file_path), "tv")

        tmdb_info = self._resolve_tmdb(slug, "tv")
        if not tmdb_info or not tmdb_info.get("id"):
            logger.warning(f"[KodiNFO] Could not resolve TMDB ID for show: {slug}")
            return False

        details = tmdb.get_full_details("tv", tmdb_info["id"])
        if not details:
            logger.warning(
                f"[KodiNFO] Could not fetch details for TMDB ID {tmdb_info['id']}"
            )
            return False

        images = tmdb.get_images("tv", tmdb_info["id"])

        if images.get("posters"):
            poster_path = os.path.join(self.output_dir, "poster.jpg")
            if tmdb.download_image(images["posters"][0], poster_path):
                images["posters"][0]

        if images.get("backdrops"):
            fanart_path = os.path.join(self.output_dir, "fanart.jpg")
            if tmdb.download_image(images["backdrops"][0], fanart_path):
                images["backdrops"][0]

        nfo_content = _build_tvshow_nfo(details)
        nfo_path = os.path.join(self.output_dir, "tvshow.nfo")
        with open(nfo_path, "w", encoding="utf-8") as f:
            f.write(nfo_content)
        logger.info(f"[KodiNFO] Created tvshow.nfo for {slug}")
        return True

    def generate_for_episode(
        self,
        slug: str | None = None,
        season_num: int | None = None,
        episode_num: int | None = None,
    ):
        """Generate episode NFO inside the season directory."""
        if slug is None:
            slug = _extract_slug_from_path(str(self.file_path), "tv")

        if season_num is None or episode_num is None:
            match = re.search(r"S(\d{2})E(\d{2})", self.file_path.stem)
            if match:
                season_num = int(match.group(1))
                episode_num = int(match.group(2))

        tmdb_info = self._resolve_tmdb(slug, "tv")
        if not tmdb_info or not tmdb_info.get("id"):
            logger.warning(f"[KodiNFO] Could not resolve TMDB ID for episode: {slug}")
            return False

        details = tmdb.get_full_details("tv", tmdb_info["id"])
        if not details:
            logger.warning(
                f"[KodiNFO] Could not fetch details for TMDB ID {tmdb_info['id']}"
            )
            return False

        nfo_content = _build_episode_nfo(details, season_num, episode_num)
        nfo_path = self.file_path.with_suffix(".nfo")
        with open(nfo_path, "w", encoding="utf-8") as f:
            f.write(nfo_content)
        logger.info(
            f"[KodiNFO] Created episode NFO for S{season_num}E{episode_num} of {slug}"
        )
        return True


def generate_kodi_metadata(file_path: str, media_type: str | None = None):
    """
    Main entry point: generate XML NFO + images for a completed download.

    Args:
        file_path: Path to the downloaded media file
        media_type: 'Film', 'TV', 'Serie', 'movie', 'tv', etc.
    """
    if not KODI_NFO_FILES:
        return

    api_key = config_manager.login.get("TMDB", "api_key", default="")
    if not api_key:
        logger.warning(
            "[KodiNFO] TMDB API key not configured. Skipping metadata generation."
        )
        return

    generator = KodiNFOGenerator(file_path)

    media_type_lower = (media_type or "").lower()
    if media_type_lower in ("film", "movie"):
        generator.generate_for_movie()
    elif media_type_lower in ("tv", "serie", "series", "show"):
        generator.generate_for_tvshow()
        generator.generate_for_episode()
    else:
        generator.generate_for_movie()
