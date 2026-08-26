# 2026

from __future__ import annotations

import logging
import os
import subprocess

from rich.live import Live

from StreamingCommunity.torrent.title_parser import TorrentResult
from StreamingCommunity.utils.console.shared import console

log = logging.getLogger(__name__)


class TorrentDownloader:
    """Download torrents via aria2c (magnet or .torrent file)."""

    def __init__(self, aria2c_path: str, download_path: str):
        self.aria2c_path = aria2c_path
        self.download_path = download_path

    def _run_aria2c(self, url: str, timeout: int = 3600) -> str | None:
        os.makedirs(self.download_path, exist_ok=True)

        cmd = [
            self.aria2c_path,
            f"--dir={self.download_path}",
            "--seed-time=0",
            f"--bt-stop-timeout={timeout}",
            "--file-allocation=none",
            "--console-log-level=notice",
            "--summary-interval=5",
            TorrentResult.safe_arg(url),
        ]

        log.info("Downloading via aria2c: %s", url[:60] + "...")

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            last_status = ""
            with Live(console=console, refresh_per_second=4, transient=True) as live:
                for line in iter(process.stdout.readline, ""):
                    line = line.strip()
                    if not line:
                        continue

                    if "Download complete:" in line:
                        live.update(f"[green]{line}")
                    elif "ETA:" in line or "Speed:" in line:
                        if line != last_status:
                            live.update(f"[cyan]{line}")
                            last_status = line
                    elif "error" in line.lower() or "fail" in line.lower():
                        live.update(f"[red]{line}")

            process.wait(timeout=timeout + 30)

            if process.returncode == 0:
                log.info("Torrent download completed successfully")
                return self.download_path

            log.warning("aria2c exited with code %d", process.returncode)
            return None

        except subprocess.TimeoutExpired:
            process.kill()
            log.error("Torrent download timed out after %ds", timeout)
            return None
        except FileNotFoundError:
            log.error("aria2c not found at: %s", self.aria2c_path)
            return None
        except OSError as e:
            log.error("Torrent download failed: %s", e)
            return None

    def download_magnet(self, magnet_url: str, timeout: int = 3600) -> str | None:
        if not magnet_url.startswith("magnet:?xt=urn:btih:"):
            log.warning("Invalid magnet URL format, rejecting")
            return None
        return self._run_aria2c(magnet_url, timeout)

    def download_torrent_file(
        self, torrent_url: str, timeout: int = 3600
    ) -> str | None:
        if not torrent_url.startswith(("http://", "https://")):
            log.warning("Invalid torrent URL format, rejecting")
            return None
        return self._run_aria2c(torrent_url, timeout)
