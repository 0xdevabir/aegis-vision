#!/usr/bin/env python3
"""Serve a host camera as MJPEG so the Docker pipeline can use it.

Docker Desktop containers cannot open the Mac/Windows webcam. Run this on the host:

    python3 scripts/webcam_bridge.py            # webcam 0 on 127.0.0.1:8090
    python3 scripts/webcam_bridge.py --source clip.mp4 --port 8090

The pipeline container reads http://host.docker.internal:8090/video (LOCAL_CAMERA_URL).
It binds to loopback by default so the camera is not exposed to the LAN; pass
--host 0.0.0.0 only if another machine must read it.
"""

import argparse
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

# No new frame for this long: stop serving the old one, so the pipeline sees the camera as lost
# instead of showing a frozen picture as live.
STALE_SECONDS = 5.0
# Still nothing: start over in a new process (a read that hangs inside the camera driver never
# returns, and macOS only lists the cameras present when the process first touched the camera API).
RESTART_SECONDS = 20.0
REOPEN_AFTER_FAILS = 10


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

    def stale_for(self) -> float:
        return time.monotonic() - self.stamp

    def run(self):
        interval = 1 / 25 if self.is_file else 0
        cap, fails = None, 0
        while True:
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

    def wait_next(self, last_seq):
        """(jpeg, seq) of the newest frame; seq == last_seq when none arrived within a second."""
        with self.cond:
            self.cond.wait_for(lambda: self.seq != last_seq, timeout=1)
            return self.jpeg, self.seq


def make_handler(grabber):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path.startswith("/snapshot"):
                jpeg, _ = grabber.wait_next(-1)
                if not jpeg or grabber.stale_for() > STALE_SECONDS:
                    return self.send_error(503, "no frame yet")
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(jpeg)))
                self.end_headers()
                return self.wfile.write(jpeg)
            if not self.path.startswith("/video"):
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
    grabber = Grabber(source, args.quality)
    grabber.start()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(grabber))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log(f"Serving {source!r} at http://{args.host}:{args.port}/video  (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(1.0)
            if os.name == "posix" and not grabber.is_file and grabber.stale_for() > RESTART_SECONDS:
                log(f"No frame from {source!r} for {RESTART_SECONDS:.0f}s - restarting the bridge")
                os.execv(sys.executable, [sys.executable] + sys.argv)       # same pid, fresh camera API
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
