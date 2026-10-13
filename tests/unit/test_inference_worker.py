"""InferenceWorker: latest-frame-wins, never blocks the caller, survives bad frames."""
import time

import numpy as np

from core.runtime.camera_worker import InferenceWorker


class SlowPipeline:
    def __init__(self, delay=0.0, fail_on=()):
        self.delay, self.fail_on, self.seen = delay, set(fail_on), []

    def run(self, frame, **_):
        n = int(frame[0, 0, 0])
        self.seen.append(n)
        time.sleep(self.delay)
        if n in self.fail_on:
            raise RuntimeError("stage blew up")
        return type("Ctx", (), {"marker": n})()


class NoSync:
    def maybe_sync(self):
        pass


def _frame(n):
    return np.full((2, 2, 3), n, np.uint8)


def _wait(cond, timeout=3):
    end = time.time() + timeout
    while time.time() < end and not cond():
        time.sleep(0.01)
    return cond()


def test_submit_never_blocks_and_latest_frame_wins():
    pipe = SlowPipeline(delay=0.3)
    w = InferenceWorker(pipe, NoSync(), {}, "cam")
    w.start()
    t0 = time.time()
    for n in range(1, 30):          # a 30-frame burst while inference is slow
        w.submit(_frame(n))
    assert time.time() - t0 < 0.2   # caller was never blocked by the 0.3 s inference
    assert _wait(lambda: w.latest()[0] is not None and w.latest()[0].marker == 29, 5)
    assert len(pipe.seen) < 10      # stale frames were dropped, not queued
    w.stop(); w.join(timeout=2)
    assert not w.is_alive()


def test_bad_frame_is_skipped_but_repeated_failures_mark_worker_failed():
    pipe = SlowPipeline(fail_on={1})
    w = InferenceWorker(pipe, NoSync(), {}, "cam", max_consecutive_errors=3)
    w.start()
    w.submit(_frame(1))
    assert _wait(lambda: len(pipe.seen) == 1)
    w.submit(_frame(2))             # a good frame after one failure: worker carries on
    assert _wait(lambda: w.latest()[0] is not None)
    assert not w.failed

    bad = SlowPipeline(fail_on={7})
    w2 = InferenceWorker(bad, NoSync(), {}, "cam", max_consecutive_errors=3)
    w2.start()
    for _ in range(6):
        w2.submit(_frame(7))
        time.sleep(0.05)
    assert _wait(lambda: w2.failed)
    w.stop(); w.join(timeout=2)
