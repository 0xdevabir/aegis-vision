#!/usr/bin/env python3
"""Serve a host camera as MJPEG so the Docker pipeline can use it.

Docker Desktop containers cannot open the Mac/Windows webcam. Run this on the host:

    python3 scripts/webcam_bridge.py            # webcam 0 on 127.0.0.1:8090
    python3 scripts/webcam_bridge.py --source clip.mp4 --port 8090

The pipeline container reads http://host.docker.internal:8090/video (LOCAL_CAMERA_URL).
Every camera on this machine is served, not only the default one:

    GET /devices                     cameras connected right now (the dashboard lists these)
    GET /video?source=1              camera 1;  ?source=device:<uid> follows one physical camera
    GET /snapshot?source=...         one JPEG

Extra cameras open on the first request and close again once nobody reads them.
It binds to loopback by default so the camera is not exposed to the LAN; pass
--host 0.0.0.0 only if another machine must read it.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import cv2

# utils/media/devices.py is plain stdlib; loaded by path so the bridge does not pull in the app.
_spec = importlib.util.spec_from_file_location(
    "aegis_devices", Path(__file__).resolve().parent.parent / "utils" / "media" / "devices.py")
devices = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(devices)

# No new frame for this long: stop serving the old one, so the pipeline sees the camera as lost
# instead of showing a frozen picture as live.
STALE_SECONDS = 5.0
# Still nothing: start over in a new process (a read that hangs inside the camera driver never
# returns, and macOS only lists the cameras present when the process first touched the camera API).
RESTART_SECONDS = 20.0
REOPEN_AFTER_FAILS = 10
# An extra camera nobody has read for this long is closed (its light goes off).
IDLE_CLOSE_SECONDS = 30.0
DEVICE_LIST_TTL = 5.0       # system_profiler takes about a second


def log(msg: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}", flush=True)      # flush: stdout is a log file


class Grabber(threading.Thread):
    def __init__(self, source, quality: int):
        super().__init__(daemon=True)
        self.source, self.quality = source, quality
        self.is_file = isinstance(source, str)
        self.jpeg = None
        self.cond = threading.Condition()
        self.seq = 0
        self.stamp = time.monotonic()       # when the newest frame arrived (start-up counts as one)
        self.last_used = time.monotonic()   # when a client last asked for a frame
        self.stopped = False

    def stale_for(self) -> float:
        return time.monotonic() - self.stamp

    def idle_for(self) -> float:
        return time.monotonic() - self.last_used

    def run(self):
        interval = 1 / 25 if self.is_file else 0
        cap, fails = None, 0
        while not self.stopped:
            if cap is None:
                cap = cv2.VideoCapture(self.source)
                if not cap.isOpened():
                    log(f"Cannot open source {self.source!r} (macOS: allow Terminal camera access) - retrying")
                    cap.release()
                    cap = None
                    time.sleep(2.0)
                    continue
            ok, frame = cap.read()
            if not ok:
                if self.is_file:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                # A camera that stops delivering (sleep, unplug) rarely recovers on the same handle.
                fails += 1
                if fails >= REOPEN_AFTER_FAILS:
                    log(f"Source {self.source!r} stopped delivering frames - reopening")
                    cap.release()
                    cap, fails = None, 0
                time.sleep(0.2)
                continue
            fails = 0
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
            if ok:
                with self.cond:
                    self.jpeg, self.seq = buf.tobytes(), self.seq + 1
                    self.stamp = time.monotonic()
                    self.cond.notify_all()
            if interval:
                time.sleep(interval)
        if cap is not None:
            cap.release()

    def wait_next(self, last_seq):
        """(jpeg, seq) of the newest frame; seq == last_seq when none arrived within a second."""
        self.last_used = time.monotonic()
        with self.cond:
            self.cond.wait_for(lambda: self.seq != last_seq, timeout=1)
            return self.jpeg, self.seq


class Cameras:
    """The default source (always open) plus any other camera of this machine, opened on demand."""

    def __init__(self, default, quality: int):
        self.default = Grabber(default, quality)
        self.default.start()
        self.quality = quality
        self.extra: dict[int, Grabber] = {}
        self.lock = threading.Lock()
        self._listed, self._listed_at = [], 0.0

    def devices(self) -> list[dict]:
        if time.monotonic() - self._listed_at > DEVICE_LIST_TTL:
            self._listed, self._listed_at = devices.list_local_cameras(), time.monotonic()
        return self._listed

    def get(self, source: str | None):
        """Grabber for ?source=..., or None when no such camera is connected."""
        if not source:
            return self.default
        if source.startswith(devices.DEVICE_PREFIX):
            uid = source[len(devices.DEVICE_PREFIX):]
            index = next((d["index"] for d in self.devices() if d["uid"] == uid), None)
        else:
            index = int(source) if source.isdigit() else None
            if index is not None and self.devices() and index >= len(self.devices()):
                index = None        # an index past the cameras listed: nothing is plugged in there
        if index is None:
            return None
        if index == self.default.source:
            return self.default
        with self.lock:
            g = self.extra.get(index)
            if g is None or g.stopped:
                g = self.extra[index] = Grabber(index, self.quality)
                g.start()
                log(f"Opened camera {index} on request")
            return g

    def tick(self):
        """Close extra cameras nobody reads. True when the process should restart."""
        with self.lock:
            for index, g in list(self.extra.items()):
                if g.idle_for() > IDLE_CLOSE_SECONDS:
                    g.stopped = True
                    del self.extra[index]
                    log(f"Closed camera {index}: no readers")
            in_use = [self.default] + [g for g in self.extra.values() if g.idle_for() < RESTART_SECONDS]
        return os.name == "posix" and any(not g.is_file and g.stale_for() > RESTART_SECONDS for g in in_use)


def make_handler(cameras):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            url = urlsplit(self.path)
            if url.path == "/devices":
                body = json.dumps({"devices": cameras.devices()}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
            grabber = cameras.get(parse_qs(url.query).get("source", [""])[0])
            if grabber is None:
                return self.send_error(404, "no such camera connected")
            if url.path == "/snapshot":
                jpeg, _ = grabber.wait_next(-1)
                if not jpeg or grabber.stale_for() > STALE_SECONDS:
                    return self.send_error(503, "no frame yet")
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(jpeg)))
                self.end_headers()
                return self.wfile.write(jpeg)
            if url.path != "/video":
                return self.send_error(404)
            if grabber.stale_for() > STALE_SECONDS:
                return self.send_error(503, "camera is not delivering frames")
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            seq = 0                 # the grabber's first frame is 1: only frames newer than now go out
            try:
                while True:
                    jpeg, new_seq = grabber.wait_next(seq)
                    if new_seq == seq:
                        if grabber.stale_for() > STALE_SECONDS:
                            return  # hang up rather than repeat an old frame: the reader reconnects
                        continue
                    seq = new_seq
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpeg))
                    self.wfile.write(jpeg + b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="0", help="webcam index or video file (default 0)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--quality", type=int, default=80)
    args = ap.parse_args()
    source = int(args.source) if args.source.isdigit() else args.source
    cameras = Cameras(source, args.quality)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(cameras))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log(f"Serving {source!r} at http://{args.host}:{args.port}/video  (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(1.0)
            if cameras.tick():
                log(f"A camera in use sent nothing for {RESTART_SECONDS:.0f}s - restarting the bridge")
                os.execv(sys.executable, [sys.executable] + sys.argv)       # same pid, fresh camera API
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
