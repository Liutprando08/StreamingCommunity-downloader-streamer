# 16.12.25

import re
import os
import subprocess
import shutil
from pathlib import Path


# External libraries
from rich.markup import escape

# Internal utilities
from StreamingCommunity.core.ui.bar_manager import DownloadBarManager
from StreamingCommunity.source.utils.tracker import context_tracker, download_tracker
from StreamingCommunity.utils.os import os_manager
from StreamingCommunity.utils.console.shared import console
from StreamingCommunity.setup import get_megatools_path


# Variable

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# megatools output (tools.c: tool_show_progress / dl.c):
#   file.mkv: 18.74% - 764.8 MiB (801,943,240 bytes) of 4.0 GiB (5.5 MiB/s)
#   file.mkv: 0.00% - 0 bytes of 4.0 GiB
#   file.mkv: 100.00% - done 4.0 GiB (avg. 5.2 MiB/s)
MEGA_PROGRESS_RE = re.compile(
    r"^(?P<file>.+?):\s+(?P<pct>\d+(?:[.,]\d+)?)%\s+-\s+"
    r"(?P<done>.+?)\s+of\s+(?P<total>[^(]+?)"
    r"(?:\s+\((?P<speed>[^)]+)\))?\s*$"
)
MEGA_DONE_RE = re.compile(
    r"^(?P<file>.+?):\s+(?P<pct>\d+(?:[.,]\d+)?)%\s+-\s+done\s+"
    r"(?P<total>.+?)\s+\(avg\.\s+(?P<speed>[^)]+)\)\s*$"
)

# The statically linked megatools build tries to load GLib's GIO modules and
# prints harmless warnings such as:
#   Dynamic loading not supported
#   Failed to load module: /usr/lib/gio/modules/libgvfsdbus.so
# Keep them out of the TUI log: they look like fatal errors but the download
# proceeds normally.
_MEGATOOLS_NOISE = (
    "Dynamic loading not supported",
    "Failed to load module:",
)


def _parse_megatools_progress(line):
    """Translate one megatools output line into a DownloadBarManager payload.

    Returns ``None`` when the line is not a progress line. The ``size`` field
    mirrors the MP4 downloader format (``done/total``) so the tracker renders
    both the same way.
    """
    if not line:
        return None

    text = _ANSI_ESCAPE_RE.sub("", line).strip()

    done_match = MEGA_DONE_RE.match(text)
    if done_match:
        total = done_match.group("total").strip()
        return {
            "task_key": "video",
            "label": "MEGA",
            "pct": 100.0,
            "speed": done_match.group("speed").strip(),
            "size": f"{total}/{total}",
        }

    match = MEGA_PROGRESS_RE.match(text)
    if not match:
        return None

    # Newer megatools print "764.8 MiB (801,943,240 bytes)"; keep the compact
    # part for the size column.
    done = match.group("done").split(" (")[0].strip()
    total = match.group("total").strip()
    speed = (match.group("speed") or "").strip()

    try:
        pct = float(match.group("pct").replace(",", "."))
    except ValueError:
        return None

    return {
        "task_key": "video",
        "label": "MEGA",
        "pct": pct,
        "speed": speed,
        "size": f"{done}/{total}",
    }


class MEGA_Downloader:
    
    # Episode patterns for series organization
    EP_PATTERNS = [
        re.compile(r'[Ss](\d{1,2})[Ee](\d{1,2})'),
        # HD4ME season packs often use dotted names such as "1x02" or
        # "02x01"; include "." as a valid separator.
        re.compile(r'[._\s-]+(\d{1,2})x(\d{1,2})', re.IGNORECASE)
    ]

    LANG_PRIORITY = [
        re.compile(r'\bita\b', re.IGNORECASE),
        re.compile(r'italian', re.IGNORECASE)
    ]
    
    VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.m4v', '.mov', '.wmv'}
    
    def __init__(self, choose_files=False, series_layout="tv"):
        self.megatools_exe = get_megatools_path()
        self.choose_files = choose_files
        # "tv" keeps the historical Serie/TV/<Show>/Season XX layout.
        # "standard" mirrors the other services: Serie/<Show>/S<season>.
        self.series_layout = series_layout
        
        if not self.megatools_exe:
            raise RuntimeError("Megatools executable not found. Please ensure it is installed.")

    def download_url(
        self,
        url,
        dest_path=None,
        *,
        series_name=None,
        season_hint=None,
        download_id=None,
    ):
        """Download a file or folder by its public url"""
        # Mirror progress into the shared tracker when the caller did not pass
        # an id explicitly (the TUI sets it in ``context_tracker``).
        if not download_id:
            download_id = context_tracker.download_id

        # The TUI Queue normally opens this entry before calling the downloader,
        # but keep the downloader self-sufficient (and safe if the entry was
        # removed) so progress always reaches the bar/activity screens.
        self._ensure_tracker_entry(download_id, dest_path)

        if "/folder/" in url:
            return self._download_folder_megatools(
                str(url).strip(),
                dest_path,
                series_name=series_name,
                season_hint=season_hint,
                download_id=download_id,
            )
        else:
            return self._download_movie_megatools(
                str(url).strip(), dest_path, download_id=download_id
            )

    @staticmethod
    def _ensure_tracker_entry(download_id, dest_path=None):
        if not download_id:
            return
        try:
            if download_id in download_tracker.downloads:
                return
            download_tracker.start_download(
                download_id,
                context_tracker.title or "Download",
                context_tracker.site_name or "MEGA",
                context_tracker.media_type or "Film",
                path=dest_path,
            )
            download_tracker.update_status(download_id, "Downloading ...")
        except Exception:
            # Tracking is best-effort: never let it break the download.
            pass

    @staticmethod
    def _terminate(process):
        try:
            process.terminate()
        except OSError:
            pass

    def _consume_megatools_output(
        self,
        process,
        bar_mgr,
        download_id=None,
        on_file=None,
    ):
        """Read megatools output, driving the progress bar and tracker.

        Returns ``True`` when the download was cancelled. Raw megatools output
        is never written straight to stdout: in the Textual TUI that bypasses
        ``ConsoleBridge`` and corrupts the screen.
        """
        stopped = False

        for raw in process.stdout or ():
            line = raw.rstrip("\r\n")
            if not line:
                continue

            if download_id and download_tracker.is_stopped(download_id):
                stopped = True
                self._terminate(process)
                break

            parsed = _parse_megatools_progress(line)
            if parsed:
                bar_mgr.handle_progress_line(parsed)
                continue

            if line.startswith("F "):
                if on_file:
                    on_file(line[2:].strip())
                continue

            if line.startswith("Downloaded "):
                bar_mgr.handle_progress_line(
                    {"task_key": "video", "label": "MEGA", "pct": 100.0}
                )
                continue

            if line.startswith(_MEGATOOLS_NOISE):
                continue

            if line.startswith("ERROR:"):
                console.print(escape(line), style="red")
                continue
            if line.startswith("WARNING:"):
                console.print(escape(line), style="yellow")
                continue

            # Anything else is informational; route it through the console so
            # the TUI log panel captures it instead of corrupting the screen.
            console.print(escape(line), style="dim")

        if not stopped and download_id and download_tracker.is_stopped(download_id):
            stopped = True
            self._terminate(process)

        return stopped

    def _mark_cancelled(self, download_id):
        if not download_id:
            return
        try:
            download_tracker.complete_download(
                download_id, success=False, error="cancelled"
            )
        except Exception:
            pass

    def _download_movie_megatools(self, url, dest_path=None, download_id=None):
        """Download a single movie file using megatools"""
        output_dir = os.path.dirname(dest_path) if dest_path else "./Movies"
        os.makedirs(output_dir, exist_ok=True)

        cmd = [str(self.megatools_exe), "dl", url, "--path", output_dir]

        with DownloadBarManager(download_id) as bar_mgr:
            bar_mgr.add_prebuilt_tasks([("video", "MEGA")])

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            if download_id:
                download_tracker.register_process(download_id, process)

            stopped = self._consume_megatools_output(
                process, bar_mgr, download_id
            )
            process.wait()

            if stopped:
                self._mark_cancelled(download_id)
                console.print("[yellow]Download annullato")
                return None

            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, process.args)

            bar_mgr.handle_progress_line(
                {"task_key": "video", "label": "MEGA", "pct": 100.0}
            )
            bar_mgr.finish_all_tasks()

        console.print("[green]Download completato!")
        return str(output_dir)

    def _download_folder_megatools(
        self,
        url,
        dest_path=None,
        *,
        series_name=None,
        season_hint=None,
        download_id=None,
    ):
        """Download and organize a series folder using megatools"""
        # Sanitize dest_path if provided
        if dest_path:
            dest_path = os_manager.get_sanitize_path(dest_path)
            base_dir = os.path.dirname(dest_path)
        else:
            base_dir = "./"

        # The legacy MEGA layout adds a "TV" level; the standard layout writes
        # directly under Serie/ so it matches the other services.
        destination_root = (
            os.path.join(base_dir, "TV")
            if self.series_layout == "tv"
            else base_dir
        )
        
        # Use a shorter temp directory name to avoid path length issues
        import uuid
        tmp_dir_name = f"_tmp_{uuid.uuid4().hex[:8]}"  # Shorter temp name
        tmp_dir = os.path.join(base_dir, tmp_dir_name)
        
        console.print("[cyan]Download Series ...")
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)
        os.makedirs(tmp_dir, exist_ok=True)

        cmd = [str(self.megatools_exe), "dl", url, "--path", tmp_dir]
        if self.choose_files:
            cmd.append("--choose-files")

        def on_file(local_path):
            if self.choose_files:
                return
            filename = local_path.split('\\')[-1].strip()
            parsed = self._parse_episode(filename)

            if parsed:
                show, season, episode, ep_title = parsed
                show = series_name or show
                ep_display = f"S{season:02d}E{episode:02d}"
                if ep_title:
                    ep_display += f" - {ep_title}"

                console.print(f"\n[cyan]Download: [yellow]{show} [magenta]{ep_display}\n")

        with DownloadBarManager(download_id) as bar_mgr:
            bar_mgr.add_prebuilt_tasks([("video", "MEGA")])

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            if download_id:
                download_tracker.register_process(download_id, process)

            stopped = self._consume_megatools_output(
                process, bar_mgr, download_id, on_file=on_file
            )
            process.wait()

            if stopped:
                self._mark_cancelled(download_id)
                console.print("[yellow]Download annullato")
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return None

            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, process.args)

            bar_mgr.handle_progress_line(
                {"task_key": "video", "label": "MEGA", "pct": 100.0}
            )
            bar_mgr.finish_all_tasks()

        language_root = self._select_language_folder(tmp_dir)
        result_path = self._organize_series(
            language_root,
            destination_root,
            series_name=series_name,
            season_hint=season_hint,
        )

        shutil.rmtree(tmp_dir)
        return result_path

    def _select_language_folder(self, base):
        """Select folder based on language priority"""
        folders = [f for f in base.iterdir() if f.is_dir()]
        if not folders:
            return base

        for rx in self.LANG_PRIORITY:
            for f in folders:
                if rx.search(f.name):
                    console.print(f"[green]Select language: {f.name}")
                    return f

        # No language folder: keep the whole root so nested season folders
        # are all processed instead of only the first one.
        return base
    
    def _organize_series(
        self,
        base,
        destination_root,
        *,
        series_name=None,
        season_hint=None,
    ):
        """Organize series files into proper structure"""
        base = Path(base)
        destination_root = Path(destination_root)
        destination_root.mkdir(parents=True, exist_ok=True)
        last_path = None
        
        for file in base.rglob("*"):
            if not file.is_file():
                continue
            
            if file.suffix.lower() not in self.VIDEO_EXTENSIONS:
                continue

            parsed = self._parse_episode(file.name)
            if not parsed:
                continue

            parsed_show, season, episode, ep_title = parsed
            show = series_name or parsed_show
            if season is None:
                season = season_hint
            if season is None:
                continue

            # Sanitize show name
            clean_show = os_manager.get_sanitize_file(show)
            if self.series_layout == "standard":
                season_dir = destination_root / clean_show / f"S{season}"
            else:
                season_dir = destination_root / clean_show / f"Season {season:02d}"
            season_dir.mkdir(parents=True, exist_ok=True)

            name = f"S{season:02d}E{episode:02d}"
            if ep_title:
                # Limit episode title length
                max_title_len = 50  # Adjust as needed
                if len(ep_title) > max_title_len:
                    ep_title = ep_title[:max_title_len]
                name += f" - {ep_title}"

            # Sanitize the final filename
            final_name = os_manager.get_sanitize_file(f"{name}{file.suffix}")
            last_path = season_dir / final_name
            
            shutil.move(file, last_path)
        
        return str(last_path.parent) if last_path else str(destination_root)

    def _parse_episode(self, filename):
        """Parse episode information from filename"""
        for rx in self.EP_PATTERNS:
            m = rx.search(filename)
            if m:
                season = int(m.group(1))
                episode = int(m.group(2))

                before = filename[:m.start()]
                after = filename[m.end():]

                show = self._clean_show_name(before)
                ep_title = self._clean_episode_title(after)

                return show, season, episode, ep_title
        return None

    def _clean_show_name(self, text):
        """Clean show name from extra characters"""
        text = re.sub(r'[-._\s]+\d*$', '', text)
        text = re.sub(r'[-._]+$', '', text)
        text = text.replace('_', ' ')
        text = re.sub(r'\s{2,}', ' ', text)
        return text.strip().title()

    def _clean_episode_title(self, text):
        """Clean episode title from quality tags"""
        text = re.sub(r'\.(mkv|mp4|avi).*$', '', text, flags=re.I)
        text = re.sub(r'[-_]', ' ', text)
        text = re.sub(r'\b(web[- ]?dl|bluray|720p|1080p|ita|eng|subs?)\b', '', text, flags=re.I)
        text = re.sub(r'\s{2,}', ' ', text).strip()
        return text if len(text) > 3 else None