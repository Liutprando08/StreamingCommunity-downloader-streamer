"""Regression tests for download robustness.

Covers the "downloads stop after a few minutes" fixes:
- MP4 downloads resume with HTTP Range after a dropped connection.
- Truncated MP4 downloads are reported as failures, never as success.
- HLS downloads retry with a freshly signed playlist URL.
- N_m3u8DL-RE non-zero exit codes surface as failures.
"""

import io
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest import mock

from StreamingCommunity.core.downloader import mp4 as mp4_module
from StreamingCommunity.core.downloader import hls as hls_module
from StreamingCommunity.core.downloader.hls import HLS_Downloader
from StreamingCommunity.source.N_m3u8 import wrapper as wrapper_module
from StreamingCommunity.source.N_m3u8.wrapper import MediaDownloader


class _FakeBarManager:
    """Minimal stand-in for DownloadBarManager (no Rich terminal output)."""

    def __init__(self, *args, **kwargs):
        self.progress = []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def add_prebuilt_tasks(self, tasks):
        pass

    def handle_progress_line(self, data):
        self.progress.append(data)

    def finish_all_tasks(self):
        pass


class _MP4Handler(BaseHTTPRequestHandler):
    # Larger than the downloader's 64 KiB chunk size so partial data is
    # actually yielded (and written) before a dropped connection is detected.
    data = b"0123456789abcdef" * (1024 * 64)  # 1 MiB
    state = {}

    def log_message(self, *args):
        pass

    def _common_headers(self, length, extra=None):
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("ETag", '"test-etag"')
        for key, value in (extra or {}).items():
            self.send_header(key, value)

    def do_HEAD(self):
        self.send_response(200)
        self._common_headers(len(self.data))
        self.end_headers()

    def do_GET(self):
        state = type(self).state
        range_header = self.headers.get("Range")
        state.setdefault("requests", []).append(range_header)
        start = 0

        if range_header:
            start = int(range_header.split("=", 1)[1].split("-", 1)[0])
            body = self.data[start:]
            self.send_response(206)
            self._common_headers(
                len(body),
                {"Content-Range": f"bytes {start}-{len(self.data) - 1}/{len(self.data)}"},
            )
        else:
            body = self.data
            self.send_response(200)
            self._common_headers(len(body))

        self.end_headers()

        should_truncate = state.get("mode") == "truncate" or (
            state.get("mode") == "resume" and not range_header and not state.get("truncated")
        )
        if should_truncate:
            state["truncated"] = True
            # Announce the full length, send half, then drop the connection.
            self.wfile.write(body[: max(len(body) // 2, 1)])
            self.wfile.flush()
            self.close_connection = True
            return

        self.wfile.write(body)


def _start_server(handler_cls):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class TestMP4Resume(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _run(self, mode, max_retries=3):
        state = {"mode": mode, "truncated": False}
        handler_cls = type("Handler", (_MP4Handler,), {"state": state})
        server = _start_server(handler_cls)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        url = f"http://127.0.0.1:{server.server_port}/video.mp4"
        output = os.path.join(self._tmp.name, "video.mp4")
        tracker = SimpleNamespace(download_id=None, site_name=None, media_type=None)

        with mock.patch.object(mp4_module, "DownloadBarManager", _FakeBarManager), \
                mock.patch.object(mp4_module, "context_tracker", tracker), \
                mock.patch.object(mp4_module, "CREATE_NFO_FILES", False), \
                mock.patch.object(mp4_module, "KODI_NFO_FILES", False), \
                mock.patch.object(mp4_module, "MAX_RETRIES", max_retries), \
                mock.patch.object(mp4_module, "MP4_RESUME", True), \
                mock.patch.object(mp4_module.signal, "signal"), \
                mock.patch.object(mp4_module.time, "sleep"):
            path, stopped = mp4_module.MP4_Downloader(url, output)

        return path, stopped, output, state

    def test_resumes_after_dropped_connection(self):
        path, stopped, output, state = self._run("resume")

        self.assertEqual(path, output)
        self.assertFalse(stopped)
        self.assertTrue(os.path.exists(output))
        self.assertFalse(os.path.exists(output + ".temp"))
        with open(output, "rb") as handle:
            self.assertEqual(handle.read(), _MP4Handler.data)

        # The retry must request only the missing bytes, not restart from zero.
        requests = state["requests"]
        self.assertEqual(len(requests), 2)
        self.assertIsNone(requests[0])
        self.assertTrue(requests[1].startswith("bytes="))

    def test_truncated_download_is_reported_as_failure(self):
        path, stopped, output, _ = self._run("truncate", max_retries=2)

        self.assertIsNone(path)
        self.assertFalse(stopped)
        self.assertFalse(os.path.exists(output))
        # The partial file is kept for a future resume, but never renamed to success.
        self.assertTrue(os.path.exists(output + ".temp"))


class _FakeMediaDownloader:
    def __init__(self, statuses, url="https://cdn.example/master.m3u8"):
        self.statuses = list(statuses)
        self.url = url
        self.parse_error = None
        self.calls = 0

    def parser_stream(self):
        return []

    def start_download(self):
        self.calls += 1
        return self.statuses.pop(0)


_SUCCESS_STATUS = {
    "video": {"path": "video.mp4"},
    "audios": [],
    "subtitles": [],
    "external_subtitles": [],
}


class TestHLSRetry(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _downloader(self, fake, resolver=None):
        output = os.path.join(self._tmp.name, "episode.mkv")
        downloader = HLS_Downloader(
            "https://cdn.example/old.m3u8", output, playlist_resolver=resolver
        )
        # _merge_files is mocked so the output file must exist for the success path.
        open(output, "wb").close()
        return downloader, output

    def _run(self, downloader, fake):
        with mock.patch.object(hls_module, "MediaDownloader", return_value=fake), \
                mock.patch.object(hls_module, "MediaPlayers"), \
                mock.patch.object(hls_module.os_manager, "create_path"), \
                mock.patch.object(hls_module, "CREATE_NFO_FILES", False), \
                mock.patch.object(hls_module, "KODI_NFO_FILES", False), \
                mock.patch.object(hls_module, "CLEANUP_TMP", False), \
                mock.patch.object(hls_module, "REFRESH_RETRIES", 3), \
                mock.patch.object(
                    HLS_Downloader, "_merge_files", return_value=downloader.output_path
                ), \
                mock.patch.object(HLS_Downloader, "_print_summary"):
            return downloader.start()

    def test_retries_with_fresh_playlist_after_token_failure(self):
        calls = []

        def resolver():
            calls.append(True)
            return "https://cdn.example/fresh.m3u8"

        fake = _FakeMediaDownloader(
            [
                {"error": "download_failed", "message": "HTTP 403 Forbidden", "exit_code": 1},
                _SUCCESS_STATUS,
            ]
        )
        downloader, output = self._downloader(fake, resolver=resolver)

        path, stopped = self._run(downloader, fake)

        self.assertEqual(path, output)
        self.assertFalse(stopped)
        self.assertEqual(fake.calls, 2)
        self.assertEqual(fake.url, "https://cdn.example/fresh.m3u8")
        self.assertEqual(len(calls), 1)

    def test_failure_without_resolver_is_not_reported_as_cancellation(self):
        fake = _FakeMediaDownloader(
            [{"error": "download_failed", "message": "boom", "exit_code": 1}]
        )
        downloader, _ = self._downloader(fake)

        path, stopped = self._run(downloader, fake)

        self.assertIsNone(path)
        self.assertFalse(stopped)
        self.assertEqual(fake.calls, 1)

    def test_cancellation_is_still_reported_as_stopped(self):
        fake = _FakeMediaDownloader([{"error": "cancelled"}])
        downloader, _ = self._downloader(fake)

        path, stopped = self._run(downloader, fake)

        self.assertIsNone(path)
        self.assertTrue(stopped)

    def test_parse_failure_retries_with_fresh_playlist(self):
        class _ParseFailOnce(_FakeMediaDownloader):
            def __init__(self, statuses):
                super().__init__(statuses)
                self.parse_calls = 0

            def parser_stream(self):
                self.parse_calls += 1
                self.parse_error = (
                    "N_m3u8DL-RE exited with code 1: HTTP 403 Forbidden"
                    if self.parse_calls == 1
                    else None
                )
                return []

        calls = []

        def resolver():
            calls.append(True)
            return "https://cdn.example/fresh.m3u8"

        fake = _ParseFailOnce([_SUCCESS_STATUS])
        downloader, output = self._downloader(fake, resolver=resolver)

        path, stopped = self._run(downloader, fake)

        self.assertEqual(path, output)
        self.assertFalse(stopped)
        self.assertEqual(fake.parse_calls, 2)
        self.assertEqual(fake.url, "https://cdn.example/fresh.m3u8")
        self.assertEqual(len(calls), 1)


class _FakeProc:
    def __init__(self, stdout, returncode):
        self.stdout = stdout
        self.returncode = returncode

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def terminate(self):
        pass


class TestM3U8ExitCode(unittest.TestCase):
    def test_helper_detects_expired_tokens(self):
        self.assertTrue(MediaDownloader._looks_like_expired_token(["ERROR : HTTP 403"]))
        self.assertTrue(MediaDownloader._looks_like_expired_token(["ERROR : token expired"]))
        self.assertFalse(MediaDownloader._looks_like_expired_token(["ERROR : disk full"]))

    def test_helper_formats_failure_with_exit_code_and_tail(self):
        message = MediaDownloader._format_failure(
            1, ["INFO : start", "ERROR : HTTP 403 Forbidden"]
        )
        self.assertIn("code 1", message)
        self.assertIn("403", message)

    def test_nonzero_exit_is_reported_as_download_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            downloader = MediaDownloader(
                "https://cdn.example/master.m3u8", tmp, "episode"
            )
            stdout = io.StringIO(
                "INFO : start downloading\nERROR : HTTP 403 Forbidden\n"
            )
            fake_proc = _FakeProc(stdout, returncode=1)

            with mock.patch.object(
                wrapper_module.subprocess, "Popen", return_value=fake_proc
            ), \
                    mock.patch.object(
                        wrapper_module, "get_n_m3u8dl_re_path", return_value="N_m3u8DL-RE"
                    ), \
                    mock.patch.object(
                        wrapper_module, "get_ffmpeg_path", return_value="ffmpeg"
                    ), \
                    mock.patch.object(
                        MediaDownloader, "determine_decryption_tool", return_value="shaka"
                    ), \
                    mock.patch.object(
                        MediaDownloader,
                        "_download_external_subtitles",
                        new=mock.AsyncMock(return_value={}),
                    ), \
                    mock.patch.object(wrapper_module, "DownloadBarManager", _FakeBarManager):
                status = downloader.start_download()

            self.assertEqual(status.get("error"), "download_failed")
            self.assertEqual(status.get("exit_code"), 1)
            self.assertTrue(status.get("token_expired"))
            self.assertEqual(downloader.exit_code, 1)


class TestBatchLoopRobustness(unittest.TestCase):
    def test_exception_in_episode_does_not_abort_batch(self):
        from StreamingCommunity.services._base import tv_download_manager

        class _Scrape:
            def getEpisodeSeasons(self, season):
                return [{"number": 1}, {"number": 2}, {"number": 3}]

        calls = []

        def download(episode, season, index):
            calls.append(episode["number"])
            if episode["number"] == 2:
                raise RuntimeError("boom")
            return f"/tmp/{episode['number']}.mkv", False

        with mock.patch.object(tv_download_manager, "console"):
            tv_download_manager.process_episode_download(
                index_season_selected=1,
                scrape_serie=_Scrape(),
                download_video_callback=download,
                download_all=True,
                episode_selection=None,
            )

        self.assertEqual(calls, [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
