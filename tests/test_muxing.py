"""Regression tests for the download -> mux pipeline.

Covers the muxing fixes:
- Audio is not shifted twice with a redundant -itsoffset.
- A failed ffmpeg join is reported as a failure and leaves no partial output.
- Audio is never truncated with -shortest.
- Subtitles carry a language tag and follow the video's container start.
- Muxing intermediates are ignored/cleaned so they are not treated as audio.
- capture_ffmpeg_real_time exposes the real ffmpeg exit code.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Import the downloader package first: it initializes StreamingCommunity.utils
# before setup.binary_paths is reached (avoids a circular import when this test
# is run directly by unittest discovery).
from StreamingCommunity.core.downloader import hls as _hls_module  # noqa: F401
from StreamingCommunity.core.processors import capture as capture_module
from StreamingCommunity.core.processors import merge as merge_module
from StreamingCommunity.services.torrent import audio_dub as audio_dub_module
from StreamingCommunity.source.N_m3u8.wrapper import MediaDownloader
from StreamingCommunity.torrent import muxer as muxer_module
from StreamingCommunity.torrent.muxer import TorrentMuxer


class _MuxTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.video = self.dir / "video.mkv"
        self.audio = self.dir / "audio.m4a"
        self.out = self.dir / "out.mkv"
        self.video.write_bytes(b"video")
        self.audio.write_bytes(b"audio")


class TestJoinAudios(_MuxTestBase):
    def test_no_double_itsoffset_and_no_shortest(self):
        seen = {}

        def fake_capture(cmd, description, log_path=None):
            seen["cmd"] = cmd
            return {}, 1

        with (
            mock.patch.object(merge_module, "get_ffmpeg_path", return_value="ffmpeg"),
            mock.patch.object(
                merge_module, "check_duration_v_a", return_value=(True, 5.0, 10.0, 5.0)
            ),
            mock.patch.object(
                merge_module, "check_sync_offset", return_value=(-83.0, False)
            ),
            mock.patch.object(
                merge_module, "capture_ffmpeg_real_time", side_effect=fake_capture
            ),
        ):
            result = merge_module.join_audios(
                str(self.video),
                [{"path": str(self.audio), "name": "ita"}],
                str(self.out),
            )

        cmd = seen["cmd"]
        self.assertNotIn("-itsoffset", cmd)
        self.assertNotIn("-shortest", cmd)
        # A failed mux must not be reported as success and must not leave a
        # partial file behind.
        self.assertIsNone(result[0])
        self.assertTrue(result[1])  # audio was detected as shorter
        self.assertFalse(self.out.exists())
        self.assertFalse((self.dir / "out.part.mkv").exists())

    def test_success_replaces_temp_output(self):
        def fake_capture(cmd, description, log_path=None):
            tmp_path = Path(cmd[cmd.index("-y") - 1])
            self.assertEqual(tmp_path.name, "out.part.mkv")
            tmp_path.write_bytes(b"muxed")
            return {"time": "00:00:10"}, 0

        with (
            mock.patch.object(merge_module, "get_ffmpeg_path", return_value="ffmpeg"),
            mock.patch.object(
                merge_module, "check_duration_v_a", return_value=(True, 0.1, 10.0, 10.0)
            ),
            mock.patch.object(
                merge_module, "check_sync_offset", return_value=(-83.0, False)
            ),
            mock.patch.object(
                merge_module, "capture_ffmpeg_real_time", side_effect=fake_capture
            ),
        ):
            merged_file, _audio_shorter, _result = merge_module.join_audios(
                str(self.video),
                [{"path": str(self.audio), "name": "ita"}],
                str(self.out),
            )

        self.assertEqual(merged_file, str(self.out))
        self.assertEqual(self.out.read_bytes(), b"muxed")
        self.assertFalse((self.dir / "out.part.mkv").exists())


class TestJoinSubtitles(_MuxTestBase):
    def test_language_tag_and_container_start_alignment(self):
        sub = self.dir / "sub.srt"
        sub.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
        seen = {}

        def fake_capture(cmd, description, log_path=None):
            seen["cmd"] = cmd
            tmp_path = Path(cmd[cmd.index("-y") - 1])
            tmp_path.write_bytes(b"muxed")
            return {}, 0

        with (
            mock.patch.object(merge_module, "get_ffmpeg_path", return_value="ffmpeg"),
            mock.patch.object(
                merge_module, "probe_stream_start", return_value=0.083333
            ),
            mock.patch.object(merge_module, "has_audio", return_value=True),
            mock.patch.object(
                merge_module, "fix_subtitle_extension", side_effect=lambda p: p
            ),
            mock.patch.object(
                merge_module, "capture_ffmpeg_real_time", side_effect=fake_capture
            ),
        ):
            merged_file, _result = merge_module.join_subtitles(
                str(self.video),
                [
                    {
                        "path": str(sub),
                        "name": "forced-ita",
                        "language": "forced-ita",
                        "lang": "forced-ita",
                    }
                ],
                str(self.out),
            )

        self.assertEqual(merged_file, str(self.out))
        cmd = seen["cmd"]
        self.assertIn("language=ita", cmd)
        self.assertIn("title=forced-ita", cmd)

        # The subtitle input is shifted by the video's container start.
        sub_index = cmd.index(str(sub))
        self.assertEqual(
            cmd[sub_index - 3 : sub_index - 1], ["-itsoffset", "0.083333"]
        )


class TestTorrentMuxer(_MuxTestBase):
    _STREAMS = {
        "video": [{"codec_type": "video"}],
        "audio": [{"codec_type": "audio"}],
        "subtitle": [],
    }

    def _run_mux(self, returncode):
        seen = {}

        def fake_capture(cmd, description, log_path=None):
            seen["cmd"] = cmd
            if returncode == 0:
                Path(cmd[cmd.index("-y") - 1]).write_bytes(b"muxed")
            return {}, returncode

        muxer = TorrentMuxer()
        muxer.ffmpeg_path = "ffmpeg"
        with (
            mock.patch.object(muxer, "detect_streams", return_value=self._STREAMS),
            mock.patch.object(
                muxer_module, "probe_stream_duration", side_effect=[10.0, 10.1]
            ),
            mock.patch.object(
                muxer_module.shutil, "disk_usage", return_value=mock.Mock(free=10**12)
            ),
            mock.patch.object(
                muxer_module, "capture_ffmpeg_real_time", side_effect=fake_capture
            ),
        ):
            result = muxer.mux_video_audio(
                str(self.video), str(self.audio), str(self.out)
            )
        return result, seen, muxer

    def test_no_double_itsoffset_and_atomic_output(self):
        result, seen, _muxer = self._run_mux(0)

        self.assertEqual(result, str(self.out))
        self.assertNotIn("-itsoffset", seen["cmd"])
        self.assertEqual(self.out.read_bytes(), b"muxed")
        self.assertFalse((self.dir / "out.part.mkv").exists())

    def test_failed_mux_keeps_no_partial_output(self):
        result, _seen, _muxer = self._run_mux(1)

        self.assertIsNone(result)
        self.assertFalse(self.out.exists())
        self.assertFalse((self.dir / "out.part.mkv").exists())


class _FakeTorrentMuxer:
    def __init__(self, valid=True, mux_result=True):
        self.valid = valid
        self.mux_result = mux_result

    def mux_video_audio(self, video_path, audio_path, output_path):
        if not self.mux_result:
            return None
        Path(output_path).write_bytes(b"dubbed")
        return output_path

    def detect_streams(self, path):
        if self.valid:
            return {
                "video": [{"codec_type": "video"}],
                "audio": [{"codec_type": "audio"}],
            }
        return {"video": [{"codec_type": "video"}], "audio": []}


class TestAudioDubValidation(_MuxTestBase):
    def _run(self, muxer):
        dubbed = self.dir / "video_ita.mkv"
        with mock.patch.object(audio_dub_module, "TorrentMuxer", return_value=muxer):
            result = audio_dub_module.mux_italian_audio(
                str(self.video), str(self.audio)
            )
        return result, dubbed

    def test_valid_dub_replaces_original(self):
        result, dubbed = self._run(_FakeTorrentMuxer(valid=True))

        self.assertEqual(result, str(dubbed))
        self.assertTrue(dubbed.exists())
        self.assertFalse(self.video.exists())
        self.assertFalse(self.audio.exists())

    def test_invalid_dub_keeps_original(self):
        result, dubbed = self._run(_FakeTorrentMuxer(valid=False))

        self.assertIsNone(result)
        self.assertFalse(dubbed.exists())
        self.assertTrue(self.video.exists())
        self.assertFalse(self.audio.exists())

    def test_failed_mux_keeps_original(self):
        result, dubbed = self._run(_FakeTorrentMuxer(mux_result=False))

        self.assertIsNone(result)
        self.assertFalse(dubbed.exists())
        self.assertTrue(self.video.exists())


class TestDownloadStatusIntermediates(unittest.TestCase):
    def test_intermediates_are_skipped_and_languages_are_exposed(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            for name in (
                "Movie.ts",
                "Movie.ita.ts",
                "Movie.ita.vtt",
                "Movie.ita.ts.temp.m4a",
                "Movie_joined.ts",
                "Movie_with_audio.mkv",
                "Movie_final.mkv",
            ):
                (output_dir / name).write_bytes(b"x")

            downloader = object.__new__(MediaDownloader)
            downloader.output_dir = output_dir
            downloader.filename = "Movie"

            status = downloader._get_download_status({}, [])

            self.assertEqual(Path(status["video"]["path"]).name, "Movie.ts")
            self.assertEqual(
                [Path(audio["path"]).name for audio in status["audios"]],
                ["Movie.ita.ts"],
            )
            self.assertEqual(status["audios"][0]["language"], "ita")

            self.assertEqual(
                [Path(sub["path"]).name for sub in status["subtitles"]],
                ["Movie.ita.vtt"],
            )
            self.assertEqual(status["subtitles"][0]["lang"], "ita")

    def test_stale_intermediates_are_removed_before_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            keep = output_dir / "Movie.ts"
            stale = [
                output_dir / "Movie.ita.ts.temp.m4a",
                output_dir / "Movie.part.mkv",
                output_dir / "Movie_joined.ts",
                output_dir / "Movie_with_audio.mkv",
                output_dir / "Movie_final.mkv",
            ]
            keep.write_bytes(b"keep")
            for path in stale:
                path.write_bytes(b"stale")

            downloader = object.__new__(MediaDownloader)
            downloader.output_dir = output_dir
            downloader._cleanup_stale_intermediates()

            self.assertTrue(keep.exists())
            for path in stale:
                self.assertFalse(path.exists(), f"{path.name} should be removed")


class TestCaptureExitCode(unittest.TestCase):
    def test_nonzero_exit_code_is_returned(self):
        progress, returncode = capture_module.capture_ffmpeg_real_time(
            [sys.executable, "-c", "import sys; sys.exit(3)"],
            "test",
        )
        self.assertIsNone(progress)
        self.assertEqual(returncode, 3)


if __name__ == "__main__":
    unittest.main()
