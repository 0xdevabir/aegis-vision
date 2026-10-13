"""ThreadedCamera must survive blips but report a stalled/dead stream."""
import threading
import time

import numpy as np

from utils.media.video_source import ThreadedCamera

FRAME = np.zeros((4, 4, 3), np.uint8)


class FakeCap:
    def __init__(self, script):
        self.script, self.i, self.gate = script, 0, threading.Event()

    def read(self):
        if self.i >= len(self.script):
            self.gate.wait(5)          # camera hangs
            return False, None
        ok = self.script[self.i]
        self.i += 1
        time.sleep(0.01)
        return (True, FRAME) if ok else (False, None)

    def isOpened(self):
        return True

    def release(self):
        self.gate.set()


def test_transient_failures_are_tolerated():
    cam = ThreadedCamera(FakeCap([True, False, False, True, True]), stall_seconds=5)
    time.sleep(0.3)
    assert not cam.stopped
    assert cam.read()[0] is True
    cam.release()


def test_stalled_stream_reports_lost_instead_of_stale_frame():
    cam = ThreadedCamera(FakeCap([True, True]), stall_seconds=0.3)
    time.sleep(0.6)
    ok, frame = cam.read()
    assert ok is False and frame is None
    cam.release()


def test_local_webcam_index_maps_to_bridge_url_only_when_set(monkeypatch):
    from utils.media import resolve_source
    monkeypatch.delenv("LOCAL_CAMERA_URL", raising=False)
    assert resolve_source(0) == 0
    monkeypatch.setenv("LOCAL_CAMERA_URL", "http://host.docker.internal:8090/video")
    assert resolve_source(0) == "http://host.docker.internal:8090/video"
    assert resolve_source("rtsp://cam/1") == "rtsp://cam/1"
