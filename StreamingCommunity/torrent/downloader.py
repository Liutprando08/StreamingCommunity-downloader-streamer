# 2026

from typing import Optional


class TorrentDownloader:
    """Download torrents via libtorrent (magnet or .torrent)."""

    def __init__(self, download_path: str): ...

    def download_magnet(self, magnet_url: str, timeout: int = 3600) -> Optional[str]: ...

    def download_torrent_file(self, torrent_url: str) -> Optional[str]: ...

    def cleanup(self, torrent_handle): ...
