"""DVR recorder: writing never blocks the caller, even when finalizing a segment is slow."""
import time

import numpy as np

from utils.media.dvr import ContinuousRecorder


def _frame(v=100):
    return np.full((48, 64, 3), v, np.uint8)


def test_write_is_nonblocking_while_segment_closes_slowly(tmp_path, monkeypatch):
    segments = []
    rec = ContinuousRecorder("cam", tmp_path, segment_seconds=0.3, min_segment_seconds=0.1,
                             target_fps=50, width=64, on_segment=segments.append)
    real_close = rec._close_locked

    def slow_close():
        time.sleep(0.5)                 # stands in for a slow Docker volume
        real_close()
    monkeypatch.setattr(rec, "_close_locked", slow_close)

    worst = 0.0
    end = time.time() + 1.5
    while time.time() < end:
        t0 = time.perf_counter()
        rec.write(_frame())
        worst = max(worst, time.perf_counter() - t0)
        time.sleep(0.02)
    rec.close()
    assert worst < 0.1, f"write() stalled for {worst:.2f}s"      # before: ~0.5 s per rotation
    assert segments, "segments should still be produced in the background"
    assert segments[0]["frame_count"] >= 2 and segments[0]["file_sha256"]


def test_close_flushes_the_open_segment(tmp_path):
    segments = []
    rec = ContinuousRecorder("cam", tmp_path, segment_seconds=60, target_fps=50, width=64,
                             on_segment=segments.append)
    for _ in range(10):
        rec.write(_frame())
        time.sleep(0.025)
    rec.close()
    assert len(segments) == 1 and segments[0]["frame_count"] >= 2
