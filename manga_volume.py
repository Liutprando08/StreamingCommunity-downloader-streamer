#!/usr/bin/env python3
"""Standalone MangaWorld volume downloader / combiner.

Downloads every chapter of a volume and packs it into a single CBZ, or merges
chapter CBZ files that were already downloaded by the main project.

Usage:
    python manga_volume.py download <manga-url-or-name> -v 116
    python manga_volume.py download <manga-url-or-name> -v 1-3 -o ./Manga
    python manga_volume.py download <manga-url-or-name> --list
    python manga_volume.py combine "Video/Manga/One Piece/Volume 116"
    python manga_volume.py combine chapter1.cbz chapter2.cbz -o volume.cbz

Dependencies: requests, beautifulsoup4
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse
from xml.sax.saxutils import escape

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Install dependencies first: pip install requests beautifulsoup4")


DEFAULT_BASE_URL = os.environ.get("MANGAWORLD_URL", "https://www.mangaworld.me").rstrip(
    "/"
)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}
NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")
PAGES_RE = re.compile(r'"pages":\[([^\]]*)\]')
INVALID_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp"}
_TLS = threading.local()


@dataclass
class Chapter:
    name: str
    number: float
    url: str
    pages: list[str] = field(default_factory=list)


@dataclass
class Volume:
    name: str
    number: float
    chapters: list[Chapter] = field(default_factory=list)


def session() -> requests.Session:
    current = getattr(_TLS, "session", None)
    if current is None:
        current = requests.Session()
        current.headers.update(HEADERS)
        _TLS.session = current
    return current


def fetch(
    url: str,
    *,
    params: dict | None = None,
    timeout: float = 30,
    retries: int = 3,
    referer: str | None = None,
) -> str:
    headers = {"Referer": referer} if referer else None
    last: Exception | None = None
    for attempt in range(retries):
        try:
            response = session().get(
                url, params=params, timeout=timeout, headers=headers
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last = exc
            if attempt + 1 < retries:
                time.sleep(0.4 * (attempt + 1))
    assert last is not None
    raise last


def download_file(
    url: str,
    destination: str,
    *,
    timeout: float = 30,
    retries: int = 3,
    referer: str | None = None,
) -> None:
    headers = {"Referer": referer} if referer else None
    last: Exception | None = None
    for attempt in range(retries):
        try:
            with session().get(
                url, timeout=timeout, headers=headers, stream=True
            ) as response:
                response.raise_for_status()
                with open(destination, "wb") as handle:
                    for chunk in response.iter_content(65536):
                        if chunk:
                            handle.write(chunk)
            return
        except (requests.RequestException, OSError) as exc:
            last = exc
            if attempt + 1 < retries:
                time.sleep(0.4 * (attempt + 1))
    assert last is not None
    raise last


def natural_key(value: str) -> list:
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", value)
    ]


def parse_number(text: str, fallback: float) -> float:
    match = NUMBER_RE.search(text or "")
    if not match:
        return float(fallback)
    try:
        return float(match.group(1))
    except ValueError:
        return float(fallback)


def safe_name(value: str) -> str:
    cleaned = INVALID_RE.sub("_", value or "").strip().strip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:180] or "untitled"


def volume_number_text(number: float) -> str:
    return str(int(number)) if float(number).is_integer() else f"{number:g}"


def parse_chapters(container, base_url: str) -> list[Chapter]:
    chapters: list[Chapter] = []
    fallback = 1
    for row in container.select(".ch-row"):
        link = row.select_one("a.ch[href]")
        if not link:
            continue
        href = link.get("href", "")
        if not isinstance(href, str) or not href:
            continue
        name_label = link.select_one(".ch-name")
        name = (
            name_label.get_text(" ", strip=True)
            if name_label
            else link.get_text(" ", strip=True)
        )
        number = parse_number(name, fallback)
        fallback = int(number) + 1
        chapters.append(
            Chapter(
                name=name or f"Capitolo {int(number)}",
                number=number,
                url=urljoin(base_url, href),
            )
        )
    return chapters


def parse_manga_page(html: str, page_url: str) -> list[Volume]:
    soup = BeautifulSoup(html, "html.parser")
    volumes: list[Volume] = []
    nodes = soup.select(".volume")

    if nodes:
        for index, node in enumerate(nodes, 1):
            label = node.select_one(".volume-name") or node.select_one(".volume-head")
            name = label.get_text(" ", strip=True) if label else f"Volume {index}"
            volumes.append(
                Volume(
                    name=name,
                    number=parse_number(name, index),
                    chapters=parse_chapters(node, page_url),
                )
            )
    else:
        chapters = parse_chapters(soup, page_url)
        if chapters:
            volumes.append(Volume(name="Volume 1", number=1.0, chapters=chapters))

    for volume in volumes:
        volume.chapters.sort(key=lambda chapter: chapter.number)
    return volumes


def extract_manga_name(html: str, page_url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for selector in (
        "h1",
        ".manga-title",
        "meta[property='og:title']",
        "title",
    ):
        node = soup.select_one(selector)
        if not node:
            continue
        text = (
            node.get("content")
            if node.name == "meta"
            else node.get_text(" ", strip=True)
        )
        if not text:
            continue
        text = re.sub(
            r"\s*[|\-–]\s*MangaWorld.*$", "", text, flags=re.IGNORECASE
        ).strip()
        if text:
            return text
    match = re.search(r"/manga/\d+[-/]([^/?#]+)", page_url)
    if match:
        return match.group(1).replace("-", " ").title()
    return "Manga"


def search_manga(
    query: str, base_url: str, timeout: float, retries: int
) -> list[tuple[str, str]]:
    html = fetch(
        f"{base_url}/archive",
        params={"keyword": query},
        timeout=timeout,
        retries=retries,
    )
    soup = BeautifulSoup(html, "html.parser")
    results: list[tuple[str, str]] = []
    seen: set[str] = set()
    for tile in soup.select("a.card-cover"):
        href = tile.get("href", "")
        if not isinstance(href, str) or not href:
            continue
        match = re.search(r"/manga/(\d+)[-/]([^/?#]+)", href)
        if not match or match.group(1) in seen:
            continue
        seen.add(match.group(1))
        image = tile.select_one("img")
        name = (
            tile.get("title")
            or (image.get("alt") if image else None)
            or match.group(2).replace("-", " ").title()
        )
        results.append((str(name).strip(), urljoin(base_url, href)))
    return results


def resolve_manga(target: str, base_url: str, args) -> tuple[str, str, str]:
    if target.startswith(("http://", "https://")):
        html = fetch(target, timeout=args.timeout, retries=args.retries)
        return extract_manga_name(html, target), target, html

    results = search_manga(target, base_url, args.timeout, args.retries)
    if not results:
        sys.exit(f"No manga found for: {target}")

    if len(results) > 1 and not args.yes:
        print("Search results:")
        for index, (name, url) in enumerate(results, 1):
            print(f"  {index}. {name}  {url}")
        if not sys.stdin.isatty():
            chosen = results[0]
        else:
            raw = input(f"Choose [1-{len(results)}] (Enter=1): ").strip() or "1"
            try:
                chosen = results[int(raw) - 1]
            except (ValueError, IndexError):
                sys.exit("Invalid selection")
    else:
        chosen = results[0]

    name, url = chosen
    html = fetch(url, timeout=args.timeout, retries=args.retries)
    return name, url, html


def select_volumes(volumes: list[Volume], selector: str | None) -> list[Volume]:
    if not volumes or not selector:
        return list(volumes)

    tokens = [token.strip() for token in selector.split(",") if token.strip()]
    selected: list[Volume] = []

    def add(volume: Volume) -> None:
        if volume not in selected:
            selected.append(volume)

    for token in tokens:
        lowered = token.lower()
        if lowered in ("all", "*"):
            return list(volumes)

        range_match = re.fullmatch(r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)", token)
        if range_match:
            low = float(range_match.group(1))
            high = float(range_match.group(2))
            matched = [v for v in volumes if low <= v.number <= high]
            if matched:
                for volume in matched:
                    add(volume)
            else:
                for index in range(int(low), int(high) + 1):
                    if 1 <= index <= len(volumes):
                        add(volumes[index - 1])
            continue

        if re.fullmatch(r"\d+(?:\.\d+)?", token):
            number = float(token)
            matched = [v for v in volumes if v.number == number]
            if matched:
                for volume in matched:
                    add(volume)
            else:
                index = int(number)
                if 1 <= index <= len(volumes):
                    add(volumes[index - 1])
                else:
                    print(f"Volume not found: {token}")
            continue

        matched = [v for v in volumes if v.name.lower() == lowered]
        if not matched:
            matched = [v for v in volumes if lowered in v.name.lower()]
        if matched:
            for volume in matched:
                add(volume)
        else:
            print(f"Volume not found: {token}")

    return selected


def chapter_page_urls(chapter_url: str, timeout: float, retries: int) -> list[str]:
    html = fetch(chapter_url, timeout=timeout, retries=retries)
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []

    for image in soup.select("img.reader-page, img.img-fluid, img[data-reader-image]"):
        src = image.get("src") or image.get("data-src") or ""
        if isinstance(src, str) and "/chapters/" in src:
            absolute = urljoin(chapter_url, src)
            if absolute not in urls:
                urls.append(absolute)
    if urls:
        return urls

    match = PAGES_RE.search(html)
    if not match:
        return []
    try:
        parsed = json.loads(f"[{match.group(1)}]")
    except ValueError:
        return []
    names = [str(item) for item in parsed if item]
    if not names:
        return []
    if names[0].startswith("http"):
        return names

    base = ""
    for image in soup.select("img"):
        src = image.get("src") or ""
        if isinstance(src, str) and "/chapters/" in src:
            base = src.rsplit("/", 1)[0]
            break
    if not base:
        return []
    return [f"{base}/{name}" for name in names]


def page_extension(url: str) -> str:
    extension = os.path.splitext(urlparse(url).path)[1].lower()
    return extension if extension in IMAGE_EXTENSIONS else ".jpg"


class Progress:
    def __init__(self, total: int, label: str) -> None:
        self.total = total
        self.label = label
        self.done = 0
        self.lock = threading.Lock()
        self.step = max(1, total // 40)

    def tick(self) -> None:
        with self.lock:
            self.done += 1
            if self.done == self.total or self.done % self.step == 0:
                print(
                    f"\r{self.label}: {self.done}/{self.total}",
                    end="",
                    flush=True,
                )

    def close(self) -> None:
        print()


def write_comicinfo(path: str, series: str, volume: Volume) -> None:
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ComicInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema">\n'
        f"  <Series>{escape(series)}</Series>\n"
        f"  <Volume>{escape(volume_number_text(volume.number))}</Volume>\n"
        f"  <Title>{escape(volume.name)}</Title>\n"
        "</ComicInfo>\n"
    )
    Path(path).write_text(xml, encoding="utf-8")


def write_archive(source_dir: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".part")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_STORED) as archive:
        for name in sorted(os.listdir(source_dir)):
            full = os.path.join(source_dir, name)
            if os.path.isfile(full):
                archive.write(full, arcname=name)
    os.replace(temporary, output)


def download_volume(volume: Volume, manga_name: str, output: Path, args) -> Path | None:
    chapters = volume.chapters
    if not chapters:
        print(f"Skip {volume.name}: no chapters")
        return None

    print(f"\n{volume.name}: {len(chapters)} chapters")

    with ThreadPoolExecutor(max_workers=min(args.workers, len(chapters))) as pool:
        futures = {
            pool.submit(
                chapter_page_urls, chapter.url, args.timeout, args.retries
            ): chapter
            for chapter in chapters
        }
        for future in as_completed(futures):
            chapter = futures[future]
            try:
                chapter.pages = future.result()
            except (requests.RequestException, ValueError) as exc:
                print(f"  {chapter.name}: page list failed ({exc})")
                chapter.pages = []
            if not chapter.pages:
                print(f"  {chapter.name}: no pages")

    total_pages = sum(len(chapter.pages) for chapter in chapters)
    if total_pages == 0:
        print(f"Skip {volume.name}: no pages found")
        return None
    print(f"  {total_pages} pages total")

    with tempfile.TemporaryDirectory(prefix="manga_volume_") as temporary_dir:
        tasks: list[tuple[int, int, str, str]] = []
        chapter_order = 0
        for chapter in chapters:
            if not chapter.pages:
                continue
            chapter_order += 1
            for page_index, page_url in enumerate(chapter.pages, 1):
                tasks.append((chapter_order, page_index, page_url, chapter.url))

        progress = Progress(len(tasks), "Downloading")
        failures: list[tuple[tuple, Exception]] = []

        def worker(task: tuple[int, int, str, str]) -> None:
            order, page_index, page_url, referer = task
            destination = os.path.join(
                temporary_dir,
                f"{order:04d}_{page_index:04d}{page_extension(page_url)}",
            )
            download_file(
                page_url,
                destination,
                timeout=args.timeout,
                retries=args.retries,
                referer=referer,
            )
            progress.tick()

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(worker, task): task for task in tasks}
            for future in as_completed(futures):
                try:
                    future.result()
                except (requests.RequestException, OSError) as exc:
                    failures.append((futures[future], exc))
        progress.close()

        for task, exc in failures[:5]:
            print(f"  Page failed: {task[2]} ({exc})")
        if len(failures) > 5:
            print(f"  ... and {len(failures) - 5} more failures")

        files = [
            name
            for name in os.listdir(temporary_dir)
            if os.path.isfile(os.path.join(temporary_dir, name))
        ]
        if not files:
            print(f"Skip {volume.name}: nothing downloaded")
            return None

        if not args.no_comicinfo:
            write_comicinfo(
                os.path.join(temporary_dir, "ComicInfo.xml"), manga_name, volume
            )

        write_archive(temporary_dir, output)

    print(f"Saved: {output}")
    return output


def volume_output_path(
    manga_name: str, volume: Volume, output: str | None, single: bool
) -> Path:
    if output:
        path = Path(output).expanduser()
        if path.suffix.lower() == ".cbz":
            if not single:
                raise SystemExit(
                    "--output must be a directory when downloading multiple volumes"
                )
            return path
        root = path
    else:
        root = Path("Video") / "Manga"
    return (
        root
        / safe_name(manga_name)
        / f"{safe_name(manga_name)} - {safe_name(volume.name)}.cbz"
    )


def print_volumes(volumes: list[Volume]) -> None:
    for index, volume in enumerate(volumes, 1):
        print(
            f"{index:>3}. {volume.name} "
            f"({len(volume.chapters)} chapters, "
            f"n={volume_number_text(volume.number)})"
        )


def cmd_download(args) -> int:
    base_url = args.base_url.rstrip("/")
    manga_name, page_url, html = resolve_manga(args.manga, base_url, args)
    volumes = parse_manga_page(html, page_url)
    if not volumes:
        sys.exit("No volumes or chapters found")

    if args.list:
        print(f"{manga_name} ({page_url})")
        print_volumes(volumes)
        return 0

    selector = args.volume
    if selector is None:
        if not sys.stdin.isatty():
            sys.exit("Specify --volume (or use --list to see the available volumes)")
        print(f"\n{manga_name}:")
        print_volumes(volumes)
        selector = input("\nVolume(s) to combine (e.g. 116, 1-3, all): ").strip()

    selected = select_volumes(volumes, selector)
    if not selected:
        sys.exit("No volumes selected")

    single = len(selected) == 1
    results: list[Path] = []
    for volume in selected:
        output = volume_output_path(manga_name, volume, args.output, single)
        if output.exists() and not args.force:
            print(f"Skip existing: {output}")
            results.append(output)
            continue
        result = download_volume(volume, manga_name, output, args)
        if result:
            results.append(result)

    print(f"\nDone: {len(results)} volume(s)")
    return 0


def cmd_combine(args) -> int:
    files: list[Path] = []
    for raw in args.paths:
        path = Path(raw).expanduser()
        if path.is_dir():
            found = sorted(path.glob("*.cbz"), key=lambda item: natural_key(item.name))
            if not found:
                sys.exit(f"No .cbz files in {path}")
            files.extend(found)
        elif path.is_file() and path.suffix.lower() == ".cbz":
            files.append(path)
        else:
            sys.exit(f"Not a .cbz file or folder: {path}")

    seen: set[Path] = set()
    unique: list[Path] = []
    for file in files:
        resolved = file.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(file)
    files = unique

    first = files[0]
    series = args.series or (
        first.parent.parent.name if first.parent.parent.name else "Manga"
    )
    volume_label = args.volume_label or first.parent.name or "Volume"

    if args.output:
        output = Path(args.output).expanduser()
        if output.suffix.lower() != ".cbz":
            output = output.with_suffix(".cbz")
    else:
        output = first.parent / (f"{safe_name(series)} - {safe_name(volume_label)}.cbz")

    if output.exists() and not args.force:
        sys.exit(f"Already exists: {output} (use --force to overwrite)")

    with tempfile.TemporaryDirectory(prefix="manga_combine_") as temporary_dir:
        chapter_index = 0
        for file in files:
            chapter_index += 1
            try:
                with zipfile.ZipFile(file) as archive:
                    entries = [info for info in archive.infolist() if not info.is_dir()]
                    entries.sort(key=lambda info: natural_key(info.filename))
                    page_index = 0
                    for info in entries:
                        base = os.path.basename(info.filename)
                        if base.lower() == "comicinfo.xml":
                            continue
                        page_index += 1
                        extension = os.path.splitext(base)[1].lower() or ".jpg"
                        destination = os.path.join(
                            temporary_dir,
                            f"{chapter_index:04d}_{page_index:04d}{extension}",
                        )
                        with (
                            archive.open(info) as source,
                            open(destination, "wb") as target,
                        ):
                            shutil.copyfileobj(source, target)
            except zipfile.BadZipFile:
                print(f"Skip broken archive: {file}")
                chapter_index -= 1

        files_out = [
            name
            for name in os.listdir(temporary_dir)
            if os.path.isfile(os.path.join(temporary_dir, name))
        ]
        if not files_out:
            sys.exit("No images found to combine")

        if not args.no_comicinfo:
            volume = Volume(name=volume_label, number=parse_number(volume_label, 1))
            write_comicinfo(
                os.path.join(temporary_dir, "ComicInfo.xml"), series, volume
            )

        write_archive(temporary_dir, output)

    print(f"Saved: {output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download a MangaWorld volume as one CBZ, or merge chapter CBZ "
            "files into a single volume."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    download = subparsers.add_parser(
        "download",
        help="Download all chapters of one or more volumes into one CBZ per volume.",
    )
    download.add_argument("manga", help="MangaWorld manga URL or search query")
    download.add_argument(
        "-v",
        "--volume",
        help="Volume number/name, comma list, range (1-3) or 'all'",
    )
    download.add_argument(
        "-o",
        "--output",
        help="Output folder (or .cbz path for a single volume)",
    )
    download.add_argument(
        "-j",
        "--workers",
        type=int,
        default=12,
        help="Concurrent downloads (default: 12)",
    )
    download.add_argument("--timeout", type=float, default=30)
    download.add_argument("--retries", type=int, default=3)
    download.add_argument("--base-url", default=DEFAULT_BASE_URL)
    download.add_argument("--list", action="store_true", help="List volumes and exit")
    download.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Pick the first search result without asking",
    )
    download.add_argument(
        "--force", action="store_true", help="Overwrite existing CBZ files"
    )
    download.add_argument("--no-comicinfo", action="store_true")
    download.set_defaults(func=cmd_download)

    combine = subparsers.add_parser(
        "combine", help="Merge existing chapter CBZ files into one volume CBZ."
    )
    combine.add_argument("paths", nargs="+", help="Volume folder or chapter .cbz files")
    combine.add_argument("-o", "--output")
    combine.add_argument("--series", help="Manga/series name for ComicInfo.xml")
    combine.add_argument("--volume-label", help="Volume label for the output name")
    combine.add_argument("--force", action="store_true")
    combine.add_argument("--no-comicinfo", action="store_true")
    combine.set_defaults(func=cmd_combine)

    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] not in (
        "download",
        "combine",
        "-h",
        "--help",
    ):
        arguments.insert(0, "download")

    parser = build_parser()
    args = parser.parse_args(arguments)
    if hasattr(args, "workers"):
        args.workers = max(1, args.workers)
    if hasattr(args, "retries"):
        args.retries = max(1, args.retries)

    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
