# 16.10.25 - MangaWorld downloader (chapters as image sets / CBZ)

from __future__ import annotations

import json
import os
import re
import tempfile
import zipfile

from bs4 import BeautifulSoup
from rich.prompt import Prompt

# Internal utilities
from StreamingCommunity.services._base import site_constants
from StreamingCommunity.services._base.tv_display_manager import manage_selection
from StreamingCommunity.utils import os_manager, start_message
from StreamingCommunity.utils.console.shared import console
from StreamingCommunity.utils.http_client import create_client, get_userAgent

# Logic
from .scrapper import GetMangaInfo

# Variable
msg = Prompt()
headers = {"user-agent": get_userAgent()}
client = create_client(headers=headers)
PAGES_RE = re.compile(r'"pages":\[([^\]]*)\]')


# ── Chapter page extraction ────────────────────────────────────────────────

def _fetch_reader_html(url: str) -> str | None:
    try:
        response = client.get(url)
        response.raise_for_status()
        return response.text
    except Exception as e:
        console.print(f"[red]Failed to fetch chapter page: {e}")
        return None


def get_chapter_page_urls(url: str) -> list[str]:
    """Return the ordered list of page image URLs for a chapter reader URL."""
    html = _fetch_reader_html(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")

    # Base directory = the folder of the first chapter image rendered in the DOM.
    base_url = ""
    for img in soup.select("img.img-fluid"):
        src = img.get("src") or ""
        if isinstance(src, str) and "cdn.mangaworld" in src and "/chapters/" in src:
            base_url = src.rsplit("/", 1)[0]
            break

    # Page file names live in the embedded `"chapter":{"pages":[...]}` payload.
    pages: list[str] = []
    match = PAGES_RE.search(html)
    if match:
        try:
            parsed = json.loads(f"[{match.group(1)}]")
            pages = [str(p) for p in parsed if p]
        except ValueError:
            pages = []

    if base_url and pages:
        return [f"{base_url}/{name}" for name in pages]

    # Fallback: use whatever reader images are present in the DOM.
    fallback = []
    for img in soup.select("img.img-fluid"):
        src = img.get("src") or ""
        if isinstance(src, str) and "cdn.mangaworld" in src and "/chapters/" in src:
            if src not in fallback:
                fallback.append(src)
    return fallback or pages


# ── Single chapter download ────────────────────────────────────────────────

def download_chapter(
    episode,
    manga_name: str,
    volume_name: str | None = None,
) -> str | None:
    """Download one chapter and package it as a `.cbz` archive.

    Returns the path to the created archive, or ``None`` on failure.
    """
    url = getattr(episode, "url", None)
    if not url:
        console.print(f"[red]No URL for chapter: {getattr(episode, 'name', '?')}")
        return None

    page_urls = get_chapter_page_urls(url)
    if not page_urls:
        console.print(f"[red]No pages found for: {getattr(episode, 'name', '?')}")
        return None

    safe_manga = os_manager.get_sanitize_file(manga_name)
    chapter_label = getattr(episode, "name", None) or f"Capitolo {getattr(episode, 'number', '')}"
    safe_chapter = os_manager.get_sanitize_file(str(chapter_label))

    folder = os.path.join(site_constants.MANGA_FOLDER, safe_manga)
    if volume_name:
        folder = os.path.join(folder, os_manager.get_sanitize_file(volume_name))
    os_manager.create_path(folder)

    cbz_path = os.path.join(folder, f"{safe_manga} - {safe_chapter}.cbz")
    console.print(f"\n[yellow]Download: [red]{site_constants.SITE_NAME} → [cyan]{safe_manga} - {chapter_label}")
    console.print(f"[cyan]Pages: [red]{len(page_urls)}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        downloaded = 0
        for index, page_url in enumerate(page_urls, 1):
            try:
                response = client.get(page_url)
                response.raise_for_status()
            except Exception as e:
                console.print(f"[red]Page {index} failed: {e}")
                continue

            ext = os.path.splitext(page_url.split("?")[0])[1] or ".jpg"
            page_path = os.path.join(tmp_dir, f"{index:03d}{ext}")
            with open(page_path, "wb") as handle:
                handle.write(response.content)
            downloaded += 1

        if downloaded == 0:
            console.print("[red]No pages could be downloaded.")
            return None

        with zipfile.ZipFile(cbz_path, "w", zipfile.ZIP_STORED) as archive:
            for name in sorted(os.listdir(tmp_dir)):
                archive.write(os.path.join(tmp_dir, name), arcname=name)

    console.print(f"[green]Saved: [white]{cbz_path}")
    return cbz_path


# ── Manga level download flow ──────────────────────────────────────────────

def download_manga(
    select_title,
    season_selection: str = None,
    episode_selection: str = None,
    scrape_serie=None,
):
    """Interactive/automated download of a manga's chapters grouped by volume."""
    start_message()

    scraper = scrape_serie or GetMangaInfo(
        url=getattr(select_title, "url", None),
        manga_name=getattr(select_title, "name", None),
    )
    volumes = scraper.get_volumes()

    if not volumes:
        console.print(
            f"[red]No volumes/chapters found for {getattr(select_title, 'name', '?')}"
        )
        return None

    manga_name = getattr(select_title, "name", None) or "Manga"

    # Volume selection (map to the same semantics as seasons)
    if season_selection is None:
        console.print("\n[cyan]Volumes:")
        for index, volume in enumerate(volumes, 1):
            console.print(
                f"  [yellow]{index}[/yellow] - {volume.name} ({len(volume.episodes)} capitoli)"
            )
        last_command = msg.ask(
            "\n[cyan]Insert [red]volume index [cyan]or [red]* [cyan]to download all "
            "or [red]1-3 [cyan]for a range of volumes"
        )
    else:
        last_command = season_selection
        console.print(f"\n[cyan]Using provided volume selection: [yellow]{season_selection}")

    selected_volumes = manage_selection(last_command, len(volumes))

    results: list[str] = []
    for volume_index in selected_volumes:
        if volume_index < 1 or volume_index > len(volumes):
            console.print(
                f"[red]Volume index {volume_index} out of range (1-{len(volumes)}), skipping."
            )
            continue

        volume = volumes[volume_index - 1]
        chapters = sorted(volume.episodes.episodes, key=lambda e: e.number or 0)
        if not chapters:
            continue

        # Chapter selection inside the volume
        if episode_selection is None:
            console.print(f"\n[cyan]Chapters in {volume.name}:")
            for index, chapter in enumerate(chapters, 1):
                console.print(f"  [yellow]{index}[/yellow] - {chapter.name}")
            chapter_command = msg.ask(
                "\n[cyan]Insert [red]chapter index [cyan]or [red]* [cyan]to download all "
                "or [red]1-3 [cyan]for a range of chapters"
            )
        else:
            chapter_command = episode_selection

        selected_chapters = manage_selection(chapter_command, len(chapters))
        for chapter_index in selected_chapters:
            if chapter_index < 1 or chapter_index > len(chapters):
                console.print(
                    f"[red]Chapter index {chapter_index} out of range "
                    f"(1-{len(chapters)}), skipping."
                )
                continue

            chapter = chapters[chapter_index - 1]
            path = download_chapter(chapter, manga_name, volume.name)
            if path:
                results.append(path)

    if not results:
        console.print("[red]Nothing was downloaded.")
        return False
    return results[0] if len(results) == 1 else results


def download_film(select_title):
    """Compatibility shim: treat a manga entry as a whole-collection download."""
    return download_manga(select_title)


def stream_chapter(
    select_title,
    season_selection: str = None,
    episode_selection: str = None,
    scrape_serie=None,
):
    """Streaming a manga is not supported; fall back to downloading the chapter(s)."""
    return download_manga(select_title, season_selection, episode_selection, scrape_serie)
