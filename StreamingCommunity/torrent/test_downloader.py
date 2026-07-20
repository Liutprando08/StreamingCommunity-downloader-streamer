# 2026
# Standalone test — python StreamingCommunity/torrent/test_downloader.py

import sys
import os
import tempfile
import shutil
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from StreamingCommunity.torrent.downloader import TorrentDownloader


MAGNET = "magnet:?xt=urn:btih:ABCDEF0123456789ABCDEF0123456789ABCDEF01&dn=Test+Movie"
TORRENT_URL = "https://itorrents.net/torrent/ABCDEF0123456789ABCDEF0123456789ABCDEF01.torrent?title=Test-Movie"


def test_rejects_bad_magnet():
    dl = TorrentDownloader("/usr/bin/aria2c", "/tmp/test")
    assert dl.download_magnet("not-a-magnet") is None
    assert dl.download_magnet("") is None
    assert dl.download_magnet("magnet:?wrong=prefix") is None
    print("  PASS: rejects bad magnet")


def test_rejects_bad_torrent_url():
    dl = TorrentDownloader("/usr/bin/aria2c", "/tmp/test")
    assert dl.download_torrent_file("ftp://bad.com/file.torrent") is None
    assert dl.download_torrent_file("not-a-url") is None
    assert dl.download_torrent_file("") is None
    print("  PASS: rejects bad torrent URL")


def test_accepts_valid_magnet():
    dl = TorrentDownloader("/usr/bin/aria2c", "/tmp/test")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        result = dl.download_magnet(MAGNET, timeout=10)
        assert result == "/tmp/test"
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "/usr/bin/aria2c"
        assert "--seed-time=0" in cmd
        assert f"--bt-stop-timeout=10" in cmd
        assert any(MAGNET in arg for arg in cmd)
    print("  PASS: accepts valid magnet")


def test_accepts_valid_torrent_url():
    dl = TorrentDownloader("/usr/bin/aria2c", "/tmp/test")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        result = dl.download_torrent_file(TORRENT_URL, timeout=10)
        assert result == "/tmp/test"
    print("  PASS: accepts valid torrent URL")


def test_returns_none_on_nonzero_exit():
    dl = TorrentDownloader("/usr/bin/aria2c", "/tmp/test")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="some error")
        result = dl.download_magnet(MAGNET)
        assert result is None
    print("  PASS: returns None on nonzero exit")


def test_returns_none_on_timeout():
    import subprocess as sp
    dl = TorrentDownloader("/usr/bin/aria2c", "/tmp/test")
    with patch("subprocess.run", side_effect=sp.TimeoutExpired(cmd="aria2c", timeout=60)):
        result = dl.download_magnet(MAGNET, timeout=5)
        assert result is None
    print("  PASS: returns None on timeout")


def test_returns_none_on_file_not_found():
    dl = TorrentDownloader("/nonexistent/aria2c", "/tmp/test")
    with patch("subprocess.run", side_effect=FileNotFoundError):
        result = dl.download_magnet(MAGNET)
        assert result is None
    print("  PASS: returns None on FileNotFoundError")


def test_returns_none_on_generic_exception():
    dl = TorrentDownloader("/usr/bin/aria2c", "/tmp/test")
    with patch("subprocess.run", side_effect=RuntimeError("boom")):
        result = dl.download_magnet(MAGNET)
        assert result is None
    print("  PASS: returns None on generic exception")


def test_creates_download_dir():
    tmp = tempfile.mkdtemp()
    try:
        sub = os.path.join(tmp, "new_subdir")
        dl = TorrentDownloader("/usr/bin/aria2c", sub)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            dl.download_magnet(MAGNET)
            assert os.path.isdir(sub)
    finally:
        shutil.rmtree(tmp)
    print("  PASS: creates download dir")


def test_command_construction():
    dl = TorrentDownloader("/usr/bin/aria2c", "/tmp/test")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        dl.download_magnet(MAGNET, timeout=120)
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "/usr/bin/aria2c"
        assert cmd[1] == "--dir=/tmp/test"
        assert cmd[2] == "--seed-time=0"
        assert cmd[3] == "--bt-stop-timeout=120"
        assert cmd[4] == "--file-allocation=none"
        assert cmd[5] == "--console-log-level=warn"
        assert cmd[6] == "--summary-interval=0"
        assert cmd[7] == MAGNET
        assert len(cmd) == 8
    print("  PASS: command construction correct")


def test_subprocess_timeout_is_buffered():
    dl = TorrentDownloader("/usr/bin/aria2c", "/tmp/test")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        dl.download_magnet(MAGNET, timeout=300)
        actual_timeout = mock_run.call_args[1]["timeout"]
        assert actual_timeout == 330, f"Expected 330, got {actual_timeout}"
    print("  PASS: subprocess timeout is timeout+30")


if __name__ == "__main__":
    print("=== TorrentDownloader Test ===\n")

    tests = [
        test_rejects_bad_magnet,
        test_rejects_bad_torrent_url,
        test_accepts_valid_magnet,
        test_accepts_valid_torrent_url,
        test_returns_none_on_nonzero_exit,
        test_returns_none_on_timeout,
        test_returns_none_on_file_not_found,
        test_returns_none_on_generic_exception,
        test_creates_download_dir,
        test_command_construction,
        test_subprocess_timeout_is_buffered,
    ]

    for t in tests:
        t()
        print()

    print("All tests passed!")
