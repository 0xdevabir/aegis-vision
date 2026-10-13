"""Resilient video capture for webcams, RTSP IP cameras, and files."""

from __future__ import annotations

import os
import time
import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger("HumanAnalysis")

class ThreadedCamera:
    """
    Continuously reads frames in a background thread.
    This prevents OpenCV's internal buffer from accumulating old frames
    when the ML pipeline runs slower than the camera's framerate,
    completely eliminating live streaming lag.

    Failure handling: a few failed reads in a row are tolerated (MJPEG/RTSP streams
    glitch), but if no new frame arrives for `stall_seconds` the camera is reported
    as lost so the caller reconnects, instead of re-serving the last frame forever.
    """
    MAX_CONSECUTIVE_FAILS = 25

    def __init__(self, cap, stall_seconds: float | None = None):
        self.cap = cap
        self.stall_seconds = stall_seconds or float(os.getenv("CAMERA_STALL_SECONDS", "8"))
        self.ret, self.frame = self.cap.read()
        self.last_ok = time.monotonic()
        self.stopped = False
        self.new_frame_event = threading.Event()
        self.new_frame_event.set()

        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()

    def _update(self):
        fails = 0
        while not self.stopped:
            ret, frame = self.cap.read()
            if not ret:
                fails += 1
                if fails >= self.MAX_CONSECUTIVE_FAILS:
                    self.ret = False
                    self.stopped = True
                    self.new_frame_event.set()
                    break
                time.sleep(0.05)
                continue
            fails = 0
            self.ret = ret
            self.frame = frame
            self.last_ok = time.monotonic()
            self.new_frame_event.set()

    def read(self):
        # Wait up to 2 seconds for a new frame
        self.new_frame_event.wait(timeout=2.0)
        self.new_frame_event.clear()
        if self.stopped and not self.ret:
            return False, None
        if time.monotonic() - self.last_ok > self.stall_seconds:
            logger.warning("No new frame for %.0fs - treating camera as lost", self.stall_seconds)
            return False, None
        return self.ret, self.frame

    def release(self):
        self.stopped = True
        self.new_frame_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)
        self.cap.release()

    def isOpened(self):
        return self.cap.isOpened() and not self.stopped

    def set(self, prop, value):
        return self.cap.set(prop, value)

    def get(self, prop):
        return self.cap.get(prop)


class FileCapture:
    """Sequential, real-time-paced reader for video files.

    ThreadedCamera drops frames by design (right for live cameras, wrong for files:
    it reads a whole clip in milliseconds and keeps only the newest frame). This
    reader delivers every frame in order at the file's own frame rate, optionally
    looping (VIDEO_LOOP=true) so a demo clip keeps the dashboard alive.
    """

    def __init__(self, cap, loop: bool = False, path: str = ""):
        self.cap = cap
        self.loop = loop
        self.path = path
        fps = cap.get(5) or 0          # cv2.CAP_PROP_FPS
        self.interval = 1.0 / fps if 1 <= fps <= 120 else 1.0 / 25
        self._next = None
        self.stopped = False

    def read(self):
        if self.stopped:
            return False, None
        ret, frame = self.cap.read()
        if not ret and self.loop:
            self.cap.set(1, 0)         # cv2.CAP_PROP_POS_FRAMES
            ret, frame = self.cap.read()
        if not ret:
            return False, None
        now = time.monotonic()
        if self._next is not None and self._next > now:
            time.sleep(self._next - now)
        self._next = max(now, self._next or now) + self.interval
        return True, frame

    def release(self):
        self.stopped = True
        self.cap.release()

    def isOpened(self):
        return self.cap.isOpened() and not self.stopped

    def set(self, prop, value):
        return self.cap.set(prop, value)

    def get(self, prop):
        return self.cap.get(prop)


VIDEO_EXTS = (".mp4", ".avi", ".mkv", ".mov", ".m4v", ".webm")


def is_video_file(source) -> bool:
    return isinstance(source, str) and source.lower().endswith(VIDEO_EXTS)


def resolve_source(source):
    """Expand env vars in source strings, e.g. ${RTSP_GATE_1}.

    Local webcam indexes map to LOCAL_CAMERA_URL when set: containers cannot see the
    host's camera, so Docker points that at scripts/webcam_bridge.py on the host.
    """
    if isinstance(source, str) and source.strip().isdigit():
        # The dashboard stores sources as text, so a webcam index comes back as "0": OpenCV would
        # treat that as a file called "0" instead of camera 0.
        source = int(source.strip())
    if not isinstance(source, str):
        bridge = os.getenv("LOCAL_CAMERA_URL", "")
        return bridge if bridge and isinstance(source, int) else source
    if source.startswith("${") and source.endswith("}"):
        env_name = source[2:-1]
        return os.getenv(env_name, source)
    if source.startswith("env:"):
        return os.getenv(source[4:], source)
    return os.path.expandvars(source)


def fresh_process_sees_webcam(index: int, timeout: float = 15.0) -> bool:
    """True if a new process can open local webcam `index`.

    macOS (AVFoundation) only lists the cameras present when a process first touches the
    camera API: a webcam plugged in later stays "out of bound" for the running pipeline
    but opens fine in a new process. Callers use this to tell "unplugged" from "stale list".
    """
    import subprocess
    import sys

    code = ("import cv2,sys,time\n"
            f"c=cv2.VideoCapture({int(index)})\n"
            "ok=False\n"
            "for _ in range(15):\n"
            "    ok=c.isOpened() and c.read()[0]\n"
            "    if ok: break\n"
            "    time.sleep(0.1)\n"
            "c.release(); sys.exit(0 if ok else 1)")
    try:
        return subprocess.run([sys.executable, "-c", code], capture_output=True,
                              timeout=timeout).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def configure_rtsp_options():
    """Prefer TCP transport for RTSP streams (more reliable on most networks)."""
    options = []
    if os.getenv("RTSP_TRANSPORT", "tcp").lower() == "tcp":
        options.append("rtsp_transport;tcp")
    
    # Increase timeouts for slow IP cameras (microseconds)
    options.append("stimeout;10000000")  # 10 sec for RTSP
    options.append("timeout;10000000")   # 10 sec for HTTP
    
    # Reduce latency for IP cameras by disabling FFMPEG buffering
    options.append("fflags;nobuffer")
    options.append("flags;low_delay")
    options.append("strict;experimental")
    
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "|".join(options)


def open_capture(source, max_retries: int = 5, retry_delay: float = 2.0):
    """Open a video source with retries (important for IP cameras)."""
    import cv2

    resolved = resolve_source(source)
    is_network = isinstance(resolved, str) and (
        resolved.startswith("rtsp://")
        or resolved.startswith("http://")
        or resolved.startswith("https://")
    )
    if is_network:
        # Low-latency FFmpeg flags are for live streams only: on files they make
        # FFmpeg drop the first frame.
        configure_rtsp_options()

    for attempt in range(1, max_retries + 1):
        # Force FFMPEG backend for network streams to respect timeout options
        if is_network:
            cap = cv2.VideoCapture(resolved, cv2.CAP_FFMPEG)
        else:
            cap = cv2.VideoCapture(resolved)
        if is_network:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if cap.isOpened():
            if is_network:
                ret, _ = cap.read()
                if not ret:
                    cap.release()
                    logger.warning(f"Open attempt {attempt}/{max_retries} failed for: {resolved}")
                    time.sleep(retry_delay)
                    continue
            logger.info(f"Opened video source: {resolved}")
            if is_video_file(resolved):
                loop = os.getenv("VIDEO_LOOP", "false").lower() == "true"
                return FileCapture(cap, loop=loop, path=resolved)
            return ThreadedCamera(cap)
        cap.release()
        logger.warning(f"Open attempt {attempt}/{max_retries} failed for: {resolved}")
        time.sleep(retry_delay)

    raise RuntimeError(f"Cannot open video source after {max_retries} attempts: {resolved}")


def read_frame_with_reconnect(cap, source, max_retries: int = 10):
    """Read a frame; reconnect on failure."""

    video_file = is_video_file(source)

    for _ in range(max_retries):
        ret, frame = cap.read()
        if ret and frame is not None:
            return cap, frame
        if video_file:
            return cap, None
        logger.warning("Frame read failed — reconnecting...")
        try:
            cap.release()
        except Exception:
            pass
        time.sleep(1.0)
        cap = open_capture(source, max_retries=3, retry_delay=1.0)
    return cap, None
