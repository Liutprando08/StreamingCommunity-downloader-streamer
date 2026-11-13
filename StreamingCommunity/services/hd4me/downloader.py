# 09.11.26 - HD4ME: download a post from its MEGA link.
#
# HD4ME is a download-only site: the post detail JSON exposes the real link in
# ``movie.test``. Most posts are single MEGA files; complete-season packs use a
# MEGA folder. A small number of older posts use an encrypted ZeroBin page on
# i.hd4me.net, which cannot be resolved automatically.

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

# Downloader
from StreamingCommunity.core.downloader import MEGA_Downloader

# Internal utilities
from StreamingCommunity.services._base import Entries, site_constants
from StreamingCommunity.source.utils.tracker import context_tracker
from StreamingCommunity.utils import os_manager, start_message
from StreamingCommunity.utils.console.shared import console

# Logic
from . import scrapper

# HD4ME titles season packs as "Show – 1 Stagione" (or "Show - 1 Stagione").
_SERIES_SEASON_RE = re.compile(
    r"\s*[–—−-]\s*(\d+)\s+Stagione\b", re.IGNORECASE
)


def _series_hints(name: str) -> tuple[str, int | None]:
    """Split a HD4ME title into the show name and an optional season hint."""
    text = str(name or "").strip()
    match = _SERIES_SEASON_RE.search(text)
    if not match:
        return text, None
    return text[: match.start()].strip(), int(match.group(1))


def download_film(select_title: Entries) -> str | None:
    """Download the MEGA file/folder linked by ``select_title``."""
    start_message()
    console.print(
        f"\n[yellow]Download: [red]{site_constants.SITE_NAME} → [cyan]{select_title.name} \n"
    )

    try:
        post = scrapper.get_post(select_title.id)
    except Exception as exc:
        console.print(f"[red]HD4ME: cannot load post {select_title.id}: {exc}")
        return None

    if post.get("online") is False:
        console.print("[red]HD4ME: this post is offline")
        return None

    movie = post.get("movie") or {}
    url = str(movie.get("test") or "").strip()
    if not url:
        console.print("[red]HD4ME: no download link found")
        return None

    host = (urlparse(url).hostname or "").lower()
    if host == "mega.nz" or host.endswith(".mega.nz"):
        is_folder = "/folder/" in url
        series_name, season_hint = _series_hints(select_title.name)
        folder = (
            site_constants.SERIES_FOLDER
            if is_folder
            else site_constants.MOVIE_FOLDER
        )
        dest_path = os.path.join(
            folder,
            os_manager.get_sanitize_file(select_title.name, select_title.year),
        )

        try:
            return MEGA_Downloader(
                choose_files=False,
                series_layout="standard" if is_folder else "tv",
            ).download_url(
                url=url,
                dest_path=dest_path,
                series_name=series_name if is_folder else None,
                season_hint=season_hint if is_folder else None,
                download_id=context_tracker.download_id,
            )
        except Exception as exc:
            console.print(f"[red]HD4ME: MEGA download failed: {exc}")
            return None

    if host == "i.hd4me.net":
        console.print(
            "[red]HD4ME: this post uses an encrypted ZeroBin link and cannot be "
            "downloaded automatically"
        )
        console.print(f"[yellow]Open it in a browser: {url}")
        return None

    console.print(f"[red]HD4ME: unsupported download host: {host or url}")
    return None
