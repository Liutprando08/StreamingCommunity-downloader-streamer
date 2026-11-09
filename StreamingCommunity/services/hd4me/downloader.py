# 09.11.26 - HD4ME: download a post from its MEGA link.
#
# HD4ME is a download-only site: the post detail JSON exposes the real link in
# ``movie.test``. Most posts are single MEGA files; complete-season packs use a
# MEGA folder. A small number of older posts use an encrypted ZeroBin page on
# i.hd4me.net, which cannot be resolved automatically.

from __future__ import annotations

import os
from urllib.parse import urlparse

# Downloader
from StreamingCommunity.core.downloader import MEGA_Downloader

# Internal utilities
from StreamingCommunity.services._base import Entries, site_constants
from StreamingCommunity.utils import os_manager, start_message
from StreamingCommunity.utils.console.shared import console

# Logic
from . import scrapper


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
        folder = (
            site_constants.SERIES_FOLDER
            if "/folder/" in url
            else site_constants.MOVIE_FOLDER
        )
        dest_path = os.path.join(
            folder,
            os_manager.get_sanitize_file(select_title.name, select_title.year),
        )

        try:
            return MEGA_Downloader(choose_files=False).download_url(
                url=url, dest_path=dest_path
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
