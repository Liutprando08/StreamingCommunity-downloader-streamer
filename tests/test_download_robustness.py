"""Regression tests for download robustness.

Covers the "downloads stop after a few minutes" fixes:
- MP4 downloads resume with HTTP Range after a dropped connection.
- Truncated MP4 downloads are reported as failures, never as success.
- HLS downloads retry with a freshly signed playlist URL.
- N_m3u8DL-RE non-zero exit codes surface as failures.
"""

import io
import json
import os
import tempfile
import threading
import time
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

    def start_download(self, resume_from=None, resume_tmp=None):
        self.calls += 1
        return self.statuses.pop(0)

    def get_resume_plan(self):
        return None


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


class _StallingProc:
    """Process stand-in that stays alive until the watchdog kills it."""

    def __init__(self):
        self.stdout = None
        self.returncode = None
        self.terminated = False

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def wait(self, timeout=None):
        if self.returncode is None:
            self.returncode = -15
        return self.returncode

    def kill(self):
        self.terminated = True
        self.returncode = -9


class TestHLSResumePlan(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.output_dir = os.path.join(self._tmp.name, "episode_hls_temp")
        os.makedirs(os.path.join(self.output_dir, "analysis_temp", "temp_analysis"))
        self.downloader = MediaDownloader(
            "https://cdn.example/master.m3u8", self.output_dir, "episode"
        )
        self.downloader.meta_selected_path = os.path.join(
            self.output_dir, "analysis_temp", "temp_analysis", "meta_selected.json"
        )

    @staticmethod
    def _stream(total=5, encrypted=False):
        segments = [
            {
                "Index": index + 1,
                "EncryptInfo": {"Method": "AES-128" if encrypted else "NONE"},
            }
            for index in range(total)
        ]
        return {
            "Resolution": "1920x1080",
            "Extension": "ts",
            "Codecs": "avc1.4d4028,mp4a.40.2",
            "Bandwidth": 3085448,
            "Playlist": {"MediaParts": [{"MediaSegments": segments}]},
        }

    def _write_meta(self, streams):
        with open(self.downloader.meta_selected_path, "w", encoding="utf-8") as handle:
            json.dump(streams, handle)

    def _write_segments(self, dir_name, indexes):
        directory = os.path.join(self.output_dir, dir_name)
        os.makedirs(directory, exist_ok=True)
        for index in indexes:
            with open(
                os.path.join(directory, f"{index:04d}.ts"), "wb"
            ) as handle:
                handle.write(b"x")
        return directory

    def test_plan_resumes_from_contiguous_prefix(self):
        self._write_meta([self._stream(total=5)])
        self._write_segments(
            "0__avc1.4d4028,mp4a.40.2_3085448_", [1, 2, 3, 5]
        )

        plan = self.downloader.get_resume_plan()

        self.assertIsNotNone(plan)
        self.assertEqual(plan["offset"], 3)
        self.assertEqual(plan["total"], 5)
        self.assertEqual(plan["ext"], "ts")

    def test_plan_is_disabled_for_encrypted_segments(self):
        self._write_meta([self._stream(total=3, encrypted=True)])
        self._write_segments(
            "0__avc1.4d4028,mp4a.40.2_3085448_", [1, 2, 3]
        )

        self.assertIsNone(self.downloader.get_resume_plan())

    def test_plan_is_disabled_for_multiple_streams(self):
        self._write_meta([self._stream(total=3), self._stream(total=3)])
        self._write_segments(
            "0__avc1.4d4028,mp4a.40.2_3085448_", [1, 2, 3]
        )

        self.assertIsNone(self.downloader.get_resume_plan())

    def test_plan_is_disabled_without_segment_index(self):
        stream = self._stream(total=3)
        del stream["Playlist"]["MediaParts"][0]["MediaSegments"][1]["Index"]
        self._write_meta([stream])

        self.assertIsNone(self.downloader.get_resume_plan())

    def test_build_resumed_status_concatenates_in_order(self):
        prefix = self._write_segments("prefix", [1, 2])
        part = self._write_segments("part", [0, 1, 2])
        with open(os.path.join(prefix, "0001.ts"), "wb") as handle:
            handle.write(b"a")
        with open(os.path.join(prefix, "0002.ts"), "wb") as handle:
            handle.write(b"b")
        with open(os.path.join(part, "0000.ts"), "wb") as handle:
            handle.write(b"c")
        with open(os.path.join(part, "0001.ts"), "wb") as handle:
            handle.write(b"d")
        with open(os.path.join(part, "0002.ts"), "wb") as handle:
            handle.write(b"e")

        status = self.downloader.build_resumed_status(
            prefix, [{"dir": part, "count": 2}], "ts"
        )

        with open(status["video"]["path"], "rb") as handle:
            self.assertEqual(handle.read(), b"abcd")

        status = self.downloader.build_resumed_status(
            prefix, [{"dir": part, "count": 2}], "ts", total=3
        )
        joined_path = status["video"]["path"]
        with open(joined_path, "rb") as handle:
            self.assertEqual(handle.read(), b"abc")

        status = self.downloader.build_resumed_status(
            prefix, [{"dir": part, "count": 2}], "ts", total=10
        )
        self.assertEqual(status["error"], "download_failed")
        self.assertIsNone(status["video"])
        self.assertFalse(os.path.exists(joined_path))


class TestDownloadWatchdog(unittest.TestCase):
    def _run_download(
        self, fake_reader, cfg_int, url="https://cdn.example/master.m3u8"
    ):
        with tempfile.TemporaryDirectory() as tmp:
            downloader = MediaDownloader(url, tmp, "episode")
            proc = _StallingProc()

            with mock.patch.object(
                wrapper_module.subprocess, "Popen", return_value=proc
            ), mock.patch.object(
                wrapper_module, "get_n_m3u8dl_re_path", return_value="N_m3u8DL-RE"
            ), mock.patch.object(
                wrapper_module, "get_ffmpeg_path", return_value="ffmpeg"
            ), mock.patch.object(
                MediaDownloader, "determine_decryption_tool", return_value="shaka"
            ), mock.patch.object(
                MediaDownloader,
                "_download_external_subtitles",
                new=mock.AsyncMock(return_value=[]),
            ), mock.patch.object(
                wrapper_module, "DownloadBarManager", _FakeBarManager
            ), mock.patch.object(
                wrapper_module, "_read_download_output", fake_reader
            ), mock.patch.object(
                wrapper_module, "_cfg_int", side_effect=cfg_int
            ):
                status = downloader.start_download()

            return status, proc

    def test_stalled_download_is_terminated(self):
        def fake_reader(stream):
            yield (
                "Vid 1920x1080 | 1/10 10.00% 1.00MB/10.00MB 0.00Bps",
                "progress",
            )
            time.sleep(2)

        def cfg_int(section, key, default=0):
            if key == "hls_stall_timeout":
                return 1
            if key == "hls_auth_error_limit":
                return 1000
            return default

        status, proc = self._run_download(fake_reader, cfg_int)

        self.assertEqual(status.get("error"), "download_failed")
        self.assertTrue(status.get("stalled"))
        self.assertFalse(status.get("token_expired"))
        self.assertTrue(proc.terminated)

    def test_signed_url_expiry_aborts_before_stall_timeout(self):
        expired_ms = int((time.time() - 1) * 1000)
        url = f"https://cdn.example/master.m3u8?e={expired_ms}&t=1"

        def fake_reader(stream):
            yield (
                "Vid 1920x1080 | 1/10 10.00% 1.00MB/10.00MB 0.00Bps",
                "progress",
            )
            time.sleep(2)

        def cfg_int(section, key, default=0):
            if key == "hls_stall_timeout":
                return 60
            if key == "hls_auth_error_limit":
                return 1000
            return default

        started = time.monotonic()
        with mock.patch.object(wrapper_module, "_URL_EXPIRY_GRACE", 1.0):
            status, proc = self._run_download(fake_reader, cfg_int, url=url)
        elapsed = time.monotonic() - started

        self.assertEqual(status.get("error"), "download_failed")
        self.assertTrue(status.get("token_expired"))
        self.assertFalse(status.get("stalled"))
        self.assertTrue(proc.terminated)
        self.assertLess(elapsed, 5)

    def test_segment_number_403_is_not_an_auth_error(self):
        def fake_reader(stream):
            yield (
                "Vid 1920x1080 | 403/1804 22.34% 1.00MB/10.00MB 0.00Bps",
                "progress",
            )
            time.sleep(2)

        def cfg_int(section, key, default=0):
            if key == "hls_stall_timeout":
                return 1
            if key == "hls_auth_error_limit":
                return 1
            return default

        status, proc = self._run_download(fake_reader, cfg_int)

        self.assertEqual(status.get("error"), "download_failed")
        self.assertTrue(status.get("stalled"))
        self.assertFalse(status.get("token_expired"))
        self.assertTrue(proc.terminated)

    def test_repeated_auth_errors_abort_immediately(self):
        def fake_reader(stream):
            for _ in range(3):
                yield (
                    "WARN : Response status code does not indicate success: "
                    "403 (Forbidden)",
                    "log",
                )
            time.sleep(2)

        def cfg_int(section, key, default=0):
            if key == "hls_auth_error_limit":
                return 3
            if key == "hls_stall_timeout":
                return 60
            return default

        status, proc = self._run_download(fake_reader, cfg_int)

        self.assertEqual(status.get("error"), "download_failed")
        self.assertTrue(status.get("token_expired"))
        self.assertFalse(status.get("stalled"))
        self.assertTrue(proc.terminated)


class TestHLSResumeFlow(unittest.TestCase):
    def test_stalled_download_resumes_instead_of_restarting(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "episode.mkv")
            resolver_calls = []

            class _ResumableFake(_FakeMediaDownloader):
                def start_download(self, resume_from=None, resume_tmp=None):
                    self.resume_args = (resume_from, resume_tmp)
                    return super().start_download(resume_from, resume_tmp)

                def get_resume_plan(self):
                    self.plan_calls = getattr(self, "plan_calls", 0) + 1
                    if self.plan_calls == 1:
                        return None
                    return {
                        "prefix_dir": os.path.join(tmp, "temp", "prefix"),
                        "first_index": 1,
                        "offset": 2,
                        "total": 4,
                        "ext": "ts",
                    }

                def build_resumed_status(self, prefix_dir, parts, ext, total=None):
                    self.built = (prefix_dir, parts, ext, total)
                    return dict(_SUCCESS_STATUS)

            fake = _ResumableFake(
                [
                    {
                        "error": "download_failed",
                        "message": "Download stalled",
                        "stalled": True,
                    },
                    {"error": None, "resume_count": 2, "resume_dir": "part"},
                ]
            )
            downloader = HLS_Downloader(
                "https://cdn.example/old.m3u8", output, playlist_resolver=lambda: (
                    resolver_calls.append(True) or "https://cdn.example/fresh.m3u8"
                )
            )
            # _merge_files is mocked, so make the success path's output exist.
            open(output, "wb").close()

            with mock.patch.object(hls_module, "MediaDownloader", return_value=fake), \
                    mock.patch.object(hls_module, "MediaPlayers"), \
                    mock.patch.object(hls_module.os_manager, "create_path"), \
                    mock.patch.object(hls_module, "CREATE_NFO_FILES", False), \
                    mock.patch.object(hls_module, "KODI_NFO_FILES", False), \
                    mock.patch.object(hls_module, "CLEANUP_TMP", False), \
                    mock.patch.object(hls_module, "REFRESH_RETRIES", 3), \
                    mock.patch.object(hls_module, "HLS_RESUME", True), \
                    mock.patch.object(
                        HLS_Downloader,
                        "_merge_files",
                        return_value=downloader.output_path,
                    ), \
                    mock.patch.object(HLS_Downloader, "_print_summary"):
                path, stopped = downloader.start()

            self.assertEqual(path, output)
            self.assertFalse(stopped)
            self.assertEqual(fake.calls, 2)
            self.assertEqual(len(resolver_calls), 1)
            self.assertEqual(fake.resume_args[0], 3)
            self.assertEqual(fake.built[1][0]["count"], 2)

    def test_existing_prefix_resumes_on_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "episode.mkv")
            resolver_calls = []

            class _StartupResumableFake(_FakeMediaDownloader):
                def start_download(self, resume_from=None, resume_tmp=None):
                    self.resume_args = (resume_from, resume_tmp)
                    return super().start_download(resume_from, resume_tmp)

                def get_resume_plan(self):
                    return {
                        "prefix_dir": os.path.join(tmp, "temp", "prefix"),
                        "first_index": 1,
                        "offset": 2,
                        "total": 4,
                        "ext": "ts",
                    }

                def build_resumed_status(self, prefix_dir, parts, ext, total=None):
                    self.built = (prefix_dir, parts, ext, total)
                    return dict(_SUCCESS_STATUS)

            fake = _StartupResumableFake(
                [
                    {"error": None, "resume_count": 2, "resume_dir": "part"},
                ]
            )
            downloader = HLS_Downloader(
                "https://cdn.example/old.m3u8",
                output,
                playlist_resolver=lambda: (
                    resolver_calls.append(True) or "https://cdn.example/fresh.m3u8"
                ),
            )
            open(output, "wb").close()

            with mock.patch.object(hls_module, "MediaDownloader", return_value=fake), \
                    mock.patch.object(hls_module, "MediaPlayers"), \
                    mock.patch.object(hls_module.os_manager, "create_path"), \
                    mock.patch.object(hls_module, "CREATE_NFO_FILES", False), \
                    mock.patch.object(hls_module, "KODI_NFO_FILES", False), \
                    mock.patch.object(hls_module, "CLEANUP_TMP", False), \
                    mock.patch.object(hls_module, "HLS_RESUME", True), \
                    mock.patch.object(
                        HLS_Downloader,
                        "_merge_files",
                        return_value=downloader.output_path,
                    ), \
                    mock.patch.object(HLS_Downloader, "_print_summary"):
                path, stopped = downloader.start()

            self.assertEqual(path, output)
            self.assertFalse(stopped)
            # No full run and no URL refresh: the existing prefix is used.
            self.assertEqual(fake.calls, 1)
            self.assertEqual(len(resolver_calls), 0)
            self.assertEqual(fake.resume_args[0], 3)
            self.assertEqual(fake.built[1][0]["count"], 2)

    def test_complete_prefix_is_merged_without_downloading(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "episode.mkv")

            class _CompleteFake(_FakeMediaDownloader):
                def start_download(self, resume_from=None, resume_tmp=None):
                    raise AssertionError("complete prefix must not download")

                def get_resume_plan(self):
                    return {
                        "prefix_dir": os.path.join(tmp, "temp", "prefix"),
                        "first_index": 1,
                        "offset": 4,
                        "total": 4,
                        "ext": "ts",
                    }

                def build_resumed_status(self, prefix_dir, parts, ext, total=None):
                    self.built = (prefix_dir, parts, ext, total)
                    return dict(_SUCCESS_STATUS)

            fake = _CompleteFake([])
            downloader = HLS_Downloader(
                "https://cdn.example/old.m3u8", output
            )
            open(output, "wb").close()

            with mock.patch.object(hls_module, "MediaDownloader", return_value=fake), \
                    mock.patch.object(hls_module, "MediaPlayers"), \
                    mock.patch.object(hls_module.os_manager, "create_path"), \
                    mock.patch.object(hls_module, "CREATE_NFO_FILES", False), \
                    mock.patch.object(hls_module, "KODI_NFO_FILES", False), \
                    mock.patch.object(hls_module, "CLEANUP_TMP", False), \
                    mock.patch.object(hls_module, "HLS_RESUME", True), \
                    mock.patch.object(
                        HLS_Downloader,
                        "_merge_files",
                        return_value=downloader.output_path,
                    ), \
                    mock.patch.object(HLS_Downloader, "_print_summary"):
                path, stopped = downloader.start()

            self.assertEqual(path, output)
            self.assertFalse(stopped)
            self.assertEqual(fake.calls, 0)
            self.assertEqual(fake.built[1], [])


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
            downloader.download_id = "test-nonzero-exit"
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
                    mock.patch.object(wrapper_module, "DownloadBarManager", _FakeBarManager), \
                    mock.patch.object(
                        wrapper_module.download_tracker, "complete_download"
                    ) as complete_mock:
                status = downloader.start_download()

            self.assertEqual(status.get("error"), "download_failed")
            self.assertEqual(status.get("exit_code"), 1)
            self.assertTrue(status.get("token_expired"))
            self.assertEqual(downloader.exit_code, 1)
            # The retry/resume layer decides when a download is finally failed.
            complete_mock.assert_not_called()


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
