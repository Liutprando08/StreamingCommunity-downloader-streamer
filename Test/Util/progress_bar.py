# 15.08.26
# Manual test for the unified download progress bar (core/ui/bar_manager.py)
#
# Run with:
#   venv/bin/python Test/Util/progress_bar.py

import io
import sys
import types
from contextlib import nullcontext

# Fix import
src_path = "/home/etsume/StreamingCommunity"
if src_path not in sys.path:
    sys.path.append(src_path)

from StreamingCommunity.core.ui import (
    CustomBarColumn,
    TransferStatsColumn,
    CompactTimeColumn,
    CompactTimeRemainingColumn,
    ColoredSegmentColumn,
    DownloadBarManager,
    SilentDownloadBarManager,
    console,
)
from StreamingCommunity.source.N_m3u8.wrapper import _read_download_output
from StreamingCommunity.source.utils.tracker import download_tracker, context_tracker


def fake_task(**kwargs):
    """Build a minimal Rich task-like object for ProgressColumn.render()."""
    defaults = {
        "completed": 50.0,
        "total": 100.0,
        "fields": {},
        "elapsed": 10.0,
        "finished_time": None,
        "time_remaining": 30.0,
        "finished": False,
        "description": "",
    }
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def test_bar_column():
    task = fake_task(completed=50, total=100)
    rendered = str(CustomBarColumn().render(task))
    assert ">" in rendered, f"expected arrow cursor in bar, got: {rendered!r}"
    assert rendered.startswith("-"), f"expected filled chars, got: {rendered!r}"
    print(f"OK: CustomBarColumn -> {rendered!r}")


def test_transfer_stats_column():
    task = fake_task(fields={"size": "5.0MB/10.0MB", "speed": "1.5MB/s", "duration": ""})
    rendered = str(TransferStatsColumn().render(task))
    assert "5.0MB" in rendered and "10.0MB" in rendered
    assert "1.5MB/s" in rendered
    print(f"OK: TransferStatsColumn -> {rendered!r}")

    compact = fake_task(fields={"compact_metrics": True})
    assert str(TransferStatsColumn().render(compact)) == ""
    print("OK: TransferStatsColumn hidden when compact_metrics")


def test_time_columns():
    elapsed = str(CompactTimeColumn().render(fake_task()))
    assert elapsed and not elapsed.startswith("--"), f"expected elapsed time, got: {elapsed!r}"
    remaining = str(CompactTimeRemainingColumn().render(fake_task()))
    assert remaining and not remaining.startswith("--"), f"expected ETA, got: {remaining!r}"
    unknown = str(CompactTimeRemainingColumn().render(fake_task(time_remaining=None)))
    assert "--:--" in unknown
    print("OK: time columns")


def test_segment_column():
    task = fake_task(fields={"segment": "3/10"})
    rendered = str(ColoredSegmentColumn().render(task))
    assert "3" in rendered and "10" in rendered
    print(f"OK: ColoredSegmentColumn -> {rendered!r}")


def test_prebuilt_tasks_order():
    with DownloadBarManager() as bm:
        order = [("video", "Video 1080p"), ("audio_ita", "Audio ITA"), ("sub_ita", "Sub ITA")]
        bm.add_prebuilt_tasks(order)
        assert list(bm.tasks) == [k for k, _ in order], f"tasks: {bm.tasks}"
        assert bm.progress is not None
        assert len(bm.progress.tasks) == 3
    print("OK: prebuilt tasks preserve order")


def test_handle_progress_line_autocreate():
    with DownloadBarManager() as bm:
        bm.handle_progress_line({"task_key": "video_1080p", "pct": 42.0, "speed": "1.2MB/s", "size": "10MB/20MB", "segments": "4/10"})
        assert "video_1080p" in bm.tasks
        tid = bm.tasks["video_1080p"]
        task = next(t for t in bm.progress.tasks if t.id == tid)
        assert task.completed == 42.0
        assert task.fields["segment"] == "4/10"
        assert task.fields["speed"] == "1.2MB/s"
        assert task.fields["size"] == "10MB/20MB"
    print("OK: handle_progress_line auto-creates + updates task")


def test_handle_progress_line_completion():
    with DownloadBarManager() as bm:
        bm.handle_progress_line({"task_key": "sub_ita", "pct": 100, "final_size": "20.5KB"})
        tid = bm.tasks["sub_ita"]
        task = next(t for t in bm.progress.tasks if t.id == tid)
        assert task.completed == 100
        assert task.fields["size"] == "20.5KB"
    print("OK: final_size marks subtitle complete")


def test_finish_all_tasks():
    with DownloadBarManager() as bm:
        bm.add_prebuilt_tasks([("video", "V"), ("audio", "A")])
        bm.finish_all_tasks()
        for tid in bm.tasks.values():
            task = next(t for t in bm.progress.tasks if t.id == tid)
            assert task.completed == 100
    print("OK: finish_all_tasks sets 100%")


def test_tracker_mirror():
    dl_id = "test_dl_progress"
    download_tracker.start_download(dl_id, "Title", "test")
    try:
        with DownloadBarManager(dl_id) as bm:
            bm.handle_progress_line({"task_key": "video_1080p", "pct": 42.0, "speed": "2MB/s", "size": "42MB/100MB", "segments": "42/100"})
            dl = download_tracker.downloads[dl_id]
            assert dl["progress"] == 42.0, f"progress={dl['progress']}"
            assert dl["speed"] == "2MB/s"
            assert dl["size"] == "42MB/100MB"
            assert dl["segments"] == "42/100"
    finally:
        download_tracker.complete_download(dl_id, success=True)
    assert dl_id not in download_tracker.downloads
    print("OK: handle_progress_line mirrors into download_tracker")


def test_gui_mode_uses_nullcontext():
    context_tracker.is_gui = True
    try:
        with DownloadBarManager() as bm:
            assert bm.progress is None, "progress must be None in GUI mode"
            bm.add_prebuilt_tasks([("video", "V")])
            bm.handle_progress_line({"task_key": "video", "pct": 50})
            assert bm.tasks["video"] == "gui"
    finally:
        context_tracker.is_gui = False
    print("OK: GUI mode disables Rich bars")


def test_silent_bar_manager():
    with SilentDownloadBarManager() as bm:
        assert bm.progress is None
        bm.add_prebuilt_tasks([("video", "V")])
        bm.handle_progress_line({"task_key": "video", "pct": 100})
        bm.finish_all_tasks()
    print("OK: SilentDownloadBarManager is a no-op")


def test_context_tracker_helpers():
    context_tracker.download_id = "ctx_test_1"
    context_tracker.site_name = "streamingcommunity"
    context_tracker.media_type = "Film"
    try:
        dl_id = None
        from StreamingCommunity.source.utils.tracker import open_context_download, close_context_download

        dl_id = open_context_download("My Movie", path="/tmp/my_movie.mp4")
        assert dl_id == "ctx_test_1"
        assert download_tracker.downloads["ctx_test_1"]["status"] == "Downloading ..."
        close_context_download(dl_id, True, path="/tmp/my_movie.mp4")
        assert "ctx_test_1" not in download_tracker.downloads
        entry = next(h for h in download_tracker.get_history() if h.get("id") == "ctx_test_1")
        assert entry["status"] == "completed"
    finally:
        download_tracker.complete_download("ctx_test_1", success=True)
        context_tracker.download_id = None
    print("OK: open/close context download helpers")


def test_read_download_output_newline_logs():
    stream = io.StringIO("INFO : hello\nWARN : world\n")
    out = list(_read_download_output(stream))
    assert out == [("INFO : hello", "log"), ("WARN : world", "log")], out
    print("OK: _read_download_output splits newline log lines")


def test_read_download_output_cr_progress():
    u1 = "Vid 1920x1080 | 6221 Kbps ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0/64 0.00% -0.00Bps --:--:--"
    u2 = "Vid 1920x1080 | 6221 Kbps ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 1/64 1.56% 1MB/64MB 1MBps 00:00:01"
    out = [t for t, _ in _read_download_output(io.StringIO(f"{u1}\r{u2}\r"))]
    assert len(out) == 2, out
    assert out[0].startswith("Vid") and "0.00%" in out[0]
    assert out[1].startswith("Vid") and "1.56%" in out[1]
    print("OK: _read_download_output splits \\r progress updates")


def test_read_download_output_concatenated_progress():
    # Real N_m3u8DL-RE behavior when stdout is piped: progress updates
    # concatenate with no separator at all.
    u1 = "Vid 1920x1080 | 6221 Kbps ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0/64 0.00% -0.00Bps --:--:--"
    u2 = "Vid 1920x1080 | 6221 Kbps ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 32/64 50.00% 320.00MB/641.93MB 4.97MBps 00:02:09"
    u3 = "Aud ita | ita ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 5/10 50.00% 5.00MB/10.00MB 1.00MBps 00:00:03"
    blob = f"16:29:10.268 INFO : Start downloading...{u1}{u2}{u3}\n"
    out = list(_read_download_output(io.StringIO(blob)))
    tokens = [t for t, _ in out]
    assert any("INFO :" in t for t in tokens), out
    assert u1 in tokens, out
    assert u2 in tokens, out
    assert u3 in tokens, out
    print("OK: _read_download_output splits concatenated progress updates")


def test_read_download_output_chunked():
    # Progress update split across read() boundaries must be reassembled.
    class ChunkStream:
        def __init__(self, text, n):
            self.text, self.n, self.pos = text, n, 0

        def read(self, size):
            if self.pos >= len(self.text):
                return ""
            chunk = self.text[self.pos : self.pos + min(self.n, size)]
            self.pos += len(chunk)
            return chunk

    u1 = "Vid 1920x1080 | 6221 Kbps ━━━━ 1/64 1.56% 1MB/64MB 1MBps 00:00:01"
    u2 = "Vid 1920x1080 | 6221 Kbps ━━━━━━━━━━━━━━━━━━━━━━━━━━ 64/64 100.00% 641.93MB/641.93MB 8.00MBps 00:10:30"
    tokens = [t for t, _ in _read_download_output(ChunkStream(u1 + u2, 31))]
    assert u1 in tokens, tokens
    assert u2 in tokens, tokens
    print("OK: _read_download_output reassembles chunk-split updates")


def main():
    test_bar_column()
    test_transfer_stats_column()
    test_time_columns()
    test_segment_column()
    test_prebuilt_tasks_order()
    test_handle_progress_line_autocreate()
    test_handle_progress_line_completion()
    test_finish_all_tasks()
    test_tracker_mirror()
    test_gui_mode_uses_nullcontext()
    test_silent_bar_manager()
    test_context_tracker_helpers()
    test_read_download_output_newline_logs()
    test_read_download_output_cr_progress()
    test_read_download_output_concatenated_progress()
    test_read_download_output_chunked()
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    sys.exit(main())
