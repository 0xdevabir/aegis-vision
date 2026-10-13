"""Tests for video source resolution."""

from utils.media import resolve_source


class TestResolveSource:
    def test_integer_passthrough(self):
        assert resolve_source(0) == 0

    def test_env_braces(self, monkeypatch):
        monkeypatch.setenv("RTSP_GATE_1", "rtsp://192.168.1.1/stream")
        assert resolve_source("${RTSP_GATE_1}") == "rtsp://192.168.1.1/stream"

    def test_env_prefix(self, monkeypatch):
        monkeypatch.setenv("CAM_URL", "rtsp://cam")
        assert resolve_source("env:CAM_URL") == "rtsp://cam"

    def test_plain_rtsp(self):
        url = "rtsp://user:pass@10.0.0.1:554/stream1"
        assert resolve_source(url) == url



class TestFileCapture:
    @staticmethod
    def _make_video(path, n=6, fps=30):
        import cv2
        import numpy as np
        w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (64, 48))
        for i in range(n):
            w.write(np.full((48, 64, 3), i * 40, np.uint8))
        w.release()

    def test_every_frame_delivered_in_order_not_just_the_last(self, tmp_path, monkeypatch):
        pytest = __import__("pytest")
        pytest.importorskip("cv2")
        from utils.media.video_source import FileCapture, open_capture
        vid = tmp_path / "clip.avi"
        self._make_video(vid)
        cap = open_capture(str(vid))
        assert isinstance(cap, FileCapture)
        seen = []
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            seen.append(int(frame[0, 0, 0]))
        cap.release()
        assert len(seen) == 6 and seen == sorted(seen)

    def test_loop_restarts_at_end(self, tmp_path, monkeypatch):
        pytest = __import__("pytest")
        pytest.importorskip("cv2")
        monkeypatch.setenv("VIDEO_LOOP", "true")
        from utils.media.video_source import open_capture
        vid = tmp_path / "clip.avi"
        self._make_video(vid, n=3, fps=120)
        cap = open_capture(str(vid))
        got = sum(1 for _ in range(8) if cap.read()[0])
        cap.release()
        assert got == 8                       # 3-frame clip served 8 reads → looped
