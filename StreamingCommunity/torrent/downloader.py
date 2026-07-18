# 2026

import logging
import os
import subprocess
from typing import Optional


log = logging.getLogger(__name__)


class TorrentDownloader:
    """Download torrents via aria2c (magnet or .torrent file)."""

    def __init__(self, aria2c_path: str, download_path: str):
        self.aria2c_path = aria2c_path
        self.download_path = download_path

    def download_magnet(self, magnet_url: str, timeout: int = 3600) -> Optional[str]:
        os.makedirs(self.download_path, exist_ok=True)

        cmd = [
            self.aria2c_path,
            f"--dir={self.download_path}",
            "--seed-time=0",
            "--bt-stop-timeout={}".format(timeout),
            "--file-allocation=none",
            "--console-log-level=warn",
            "--summary-interval=0",
            magnet_url,
        ]

        log.info("Downloading torrent via aria2c: %s", magnet_url[:60] + "...")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 30,
            )

            if result.returncode == 0:
                log.info("Torrent download completed successfully")
                return self.download_path

            log.warning("aria2c exited with code %d: %s", result.returncode, result.stderr.strip())
            return None

        except subprocess.TimeoutExpired:
            log.error("Torrent download timed out after %ds", timeout)
            return None
        except FileNotFoundError:
            log.error("aria2c not found at: %s", self.aria2c_path)
            return None
        except Exception as e:
            log.error("Torrent download failed: %s", e)
            return None

    def download_torrent_file(self, torrent_url: str, timeout: int = 3600) -> Optional[str]:
        os.makedirs(self.download_path, exist_ok=True)

        cmd = [
            self.aria2c_path,
            f"--dir={self.download_path}",
            "--seed-time=0",
            "--bt-stop-timeout={}".format(timeout),
            "--file-allocation=none",
            "--console-log-level=warn",
            "--summary-interval=0",
            torrent_url,
        ]

        log.info("Downloading .torrent file via aria2c: %s", torrent_url[:60] + "...")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 30,
            )

            if result.returncode == 0:
                log.info("Torrent download completed successfully")
                return self.download_path

            log.warning("aria2c exited with code %d: %s", result.returncode, result.stderr.strip())
            return None

        except subprocess.TimeoutExpired:
            log.error("Torrent download timed out after %ds", timeout)
            return None
        except FileNotFoundError:
            log.error("aria2c not found at: %s", self.aria2c_path)
            return None
        except Exception as e:
            log.error("Torrent download failed: %s", e)
            return None
