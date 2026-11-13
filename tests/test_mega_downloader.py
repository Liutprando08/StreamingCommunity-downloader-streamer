from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from StreamingCommunity.core.downloader import mega as mega_module
from StreamingCommunity.core.downloader.mega import (
    MEGA_Downloader,
    _parse_megatools_progress,
)


class _FakeBarManager:
    """Minimal DownloadBarManager stand-in that records progress updates."""

    def __init__(self, *args, **kwargs):
        self.progress = []
        self.prebuilt = []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def add_prebuilt_tasks(self, tasks):
        self.prebuilt.extend(tasks)

    def handle_progress_line(self, data):
        self.progress.append(data)

    def finish_all_tasks(self):
        pass


class _FakeProcess:
    def __init__(self, lines=(), returncode=0):
        self.stdout = list(lines)
        self.returncode = returncode
        self.args = ["megatools", "dl"]
        self.terminated = False

    def wait(self):
        return self.returncode

    def terminate(self):
        self.terminated = True


def _downloader(layout="standard"):
    # Bypass __init__ so the test does not need megatools installed.
    instance = object.__new__(MEGA_Downloader)
    instance.megatools_exe = "/bin/true"
    instance.choose_files = False
    instance.series_layout = layout
    return instance


class TestMegatoolsProgressParser(unittest.TestCase):
    def test_start_line(self):
        parsed = _parse_megatools_progress(
            "file.mkv: 0.00% - 0 bytes of 4.0 GiB"
        )

        self.assertEqual(parsed["pct"], 0.0)
        self.assertEqual(parsed["speed"], "")
        self.assertEqual(parsed["size"], "0 bytes/4.0 GiB")
        self.assertEqual(parsed["task_key"], "video")

    def test_regular_line(self):
        parsed = _parse_megatools_progress(
            "VOL. 3 - FLAC.zip: 18.74% - 764.8 MiB (801,943,240 bytes) "
            "of 4.0 GiB (5.5 MiB/s)"
        )

        self.assertEqual(parsed["pct"], 18.74)
        self.assertEqual(parsed["speed"], "5.5 MiB/s")
        self.assertEqual(parsed["size"], "764.8 MiB/4.0 GiB")

    def test_done_line(self):
        parsed = _parse_megatools_progress(
            "VOL. 3 - FLAC.zip: 100.00% - done 4.0 GiB (avg. 5.2 MiB/s)"
        )

        self.assertEqual(parsed["pct"], 100.0)
        self.assertEqual(parsed["speed"], "5.2 MiB/s")
        self.assertEqual(parsed["size"], "4.0 GiB/4.0 GiB")

    def test_comma_decimal_separator(self):
        parsed = _parse_megatools_progress(
            "Show.1x02.mkv: 18,74% - 764,8 MiB of 4,0 GiB (5,5 MiB/s)"
        )

        self.assertEqual(parsed["pct"], 18.74)
        self.assertEqual(parsed["size"], "764,8 MiB/4,0 GiB")

    def test_static_build_byte_unit(self):
        # The bundled megatools prints LONG_FORMAT without thousands separators.
        parsed = _parse_megatools_progress(
            "Film.mkv: 0.05% - 692.9 KiB (709520 byte) of 1.3 GiB "
            "(620.3 KiB/s)"
        )

        self.assertEqual(parsed["pct"], 0.05)
        self.assertEqual(parsed["size"], "692.9 KiB/1.3 GiB")

    def test_non_progress_lines(self):
        for line in (
            "F /tmp/file.mkv",
            "Downloaded /tmp/file.mkv",
            "ERROR: Download failed",
            "WARNING: chunk download failed",
            "Dynamic loading not supported",
            "Failed to load module: /usr/lib/gio/modules/libgvfsdbus.so",
            "",
        ):
            self.assertIsNone(_parse_megatools_progress(line))


class TestConsumeOutput(unittest.TestCase):
    def test_gio_noise_is_suppressed(self):
        lines = [
            "Dynamic loading not supported\n",
            "Failed to load module: /usr/lib/gio/modules/libgvfsdbus.so\n",
            "Film.mkv: 0.05% - 692.9 KiB (709520 byte) of 1.3 GiB "
            "(620.3 KiB/s)\n",
        ]
        process = _FakeProcess(lines)
        bar = _FakeBarManager()

        with mock.patch.object(mega_module, "console") as console:
            stopped = _downloader()._consume_megatools_output(process, bar)

        self.assertFalse(stopped)
        self.assertEqual(len(bar.progress), 1)
        console.print.assert_not_called()


class TestTrackerRegistration(unittest.TestCase):
    def test_missing_tracker_entry_is_created(self):
        obj = _downloader()

        with (
            mock.patch.object(
                obj, "_download_movie_megatools", return_value="/tmp/out"
            ),
            mock.patch.object(mega_module, "download_tracker") as tracker,
            mock.patch.object(mega_module, "context_tracker") as ctx,
        ):
            tracker.downloads = {}
            ctx.title = "Film"
            ctx.site_name = "HD4ME"
            ctx.media_type = "Film"

            result = obj.download_url(
                "https://mega.nz/file/x#y",
                "/tmp/Movie/x.mkv",
                download_id="dl-9",
            )

        self.assertEqual(result, "/tmp/out")
        tracker.start_download.assert_called_once()
        self.assertEqual(tracker.start_download.call_args.args[0], "dl-9")
        tracker.update_status.assert_called_once_with("dl-9", "Downloading ...")


class TestMovieDownloadProgress(unittest.TestCase):
    def test_reports_progress_and_marks_completion(self):
        lines = [
            "F /tmp/file.mkv\n",
            "file.mkv: 0.00% - 0 bytes of 4.0 GiB\n",
            "file.mkv: 18.74% - 764.8 MiB (801,943,240 bytes) "
            "of 4.0 GiB (5.5 MiB/s)\n",
            "file.mkv: 100.00% - done 4.0 GiB (avg. 5.2 MiB/s)\n",
            "Downloaded /tmp/file.mkv\n",
        ]
        process = _FakeProcess(lines)
        bar = _FakeBarManager()

        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "Movie", "file.mkv")
            with (
                mock.patch.object(
                    mega_module.subprocess, "Popen", return_value=process
                ),
                mock.patch.object(
                    mega_module, "DownloadBarManager", return_value=bar
                ),
                mock.patch.object(mega_module, "download_tracker") as tracker,
            ):
                tracker.is_stopped.return_value = False
                result = _downloader()._download_movie_megatools(
                    "https://mega.nz/file/x#y", dest, download_id="dl-1"
                )

        self.assertEqual(result, os.path.dirname(dest))
        self.assertEqual(bar.prebuilt, [("video", "MEGA")])
        percentages = [item["pct"] for item in bar.progress]
        self.assertIn(18.74, percentages)
        self.assertEqual(percentages[-1], 100.0)
        tracker.register_process.assert_called_once_with("dl-1", process)
        tracker.complete_download.assert_not_called()

    def test_cancellation_terminates_process(self):
        process = _FakeProcess(["file.mkv: 0.00% - 0 bytes of 4.0 GiB\n"])
        bar = _FakeBarManager()

        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "Movie", "file.mkv")
            with (
                mock.patch.object(
                    mega_module.subprocess, "Popen", return_value=process
                ),
                mock.patch.object(
                    mega_module, "DownloadBarManager", return_value=bar
                ),
                mock.patch.object(mega_module, "download_tracker") as tracker,
            ):
                tracker.is_stopped.return_value = True
                result = _downloader()._download_movie_megatools(
                    "https://mega.nz/file/x#y", dest, download_id="dl-2"
                )

        self.assertIsNone(result)
        self.assertTrue(process.terminated)
        tracker.complete_download.assert_called_once_with(
            "dl-2", success=False, error="cancelled"
        )


class TestFolderDownloadProgress(unittest.TestCase):
    def test_folder_logs_episode_names_and_organizes(self):
        lines = [
            "F /tmp/_tmp/Breaking.Bad.S01E01.mkv\n",
            "Breaking.Bad.S01E01.mkv: 10.00% - 1.0 GiB "
            "(1,073,741,824 bytes) of 10.0 GiB (4.0 MiB/s)\n",
            "Breaking.Bad.S01E01.mkv: 100.00% - done 10.0 GiB (avg. 4.0 MiB/s)\n",
        ]
        process = _FakeProcess(lines)
        bar = _FakeBarManager()

        with tempfile.TemporaryDirectory() as tmp:
            obj = _downloader("standard")
            language_root = os.path.join(tmp, "lang")
            os.makedirs(language_root)
            dest = os.path.join(tmp, "Serie", "Breaking Bad")

            with (
                mock.patch.object(
                    mega_module.subprocess, "Popen", return_value=process
                ),
                mock.patch.object(
                    mega_module, "DownloadBarManager", return_value=bar
                ),
                mock.patch.object(mega_module, "download_tracker") as tracker,
                mock.patch.object(
                    obj, "_select_language_folder", return_value=language_root
                ),
                mock.patch.object(
                    obj, "_organize_series", return_value="ok"
                ),
                mock.patch.object(mega_module, "console") as console,
            ):
                tracker.is_stopped.return_value = False
                result = obj._download_folder_megatools(
                    "https://mega.nz/folder/abc#def",
                    dest_path=dest,
                    series_name="Breaking Bad",
                    season_hint=1,
                    download_id="dl-3",
                )

        self.assertEqual(result, "ok")
        printed = " ".join(str(call.args[0]) for call in console.print.call_args_list)
        self.assertIn("S01E01", printed)
        self.assertIn("Breaking Bad", printed)
        percentages = [item["pct"] for item in bar.progress]
        self.assertIn(10.0, percentages)
        self.assertEqual(percentages[-1], 100.0)


if __name__ == "__main__":
    unittest.main()
