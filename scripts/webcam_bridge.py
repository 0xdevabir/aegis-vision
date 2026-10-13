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
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2


class Grabber(threading.Thread):
    def __init__(self, source, quality: int):
        super().__init__(daemon=True)
        self.source, self.quality = source, quality
        self.jpeg = None
        self.cond = threading.Condition()
        self.seq = 0

    def run(self):
        is_file = isinstance(self.source, str)
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            raise SystemExit(f"Cannot open source {self.source!r} (macOS: allow Terminal camera access)")
        interval = 1 / 25 if is_file else 0
        while True:
            ok, frame = cap.read()
            if not ok:
                if is_file:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                time.sleep(0.5)
                continue
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
            if ok:
                with self.cond:
                    self.jpeg, self.seq = buf.tobytes(), self.seq + 1
                    self.cond.notify_all()
            if interval:
                time.sleep(interval)

    def wait_next(self, last_seq):
        with self.cond:
            self.cond.wait_for(lambda: self.seq != last_seq, timeout=5)
            return self.jpeg, self.seq


def make_handler(grabber):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path.startswith("/snapshot"):
                jpeg, _ = grabber.wait_next(-1)
                if not jpeg:
                    return self.send_error(503, "no frame yet")
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(jpeg)))
                self.end_headers()
                return self.wfile.write(jpeg)
            if not self.path.startswith("/video"):
                return self.send_error(404)
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            seq = -1
            try:
                while True:
                    jpeg, seq = grabber.wait_next(seq)
                    if jpeg is None:
                        continue
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
    print(f"Serving {source!r} at http://{args.host}:{args.port}/video  (Ctrl+C to stop)")
    ThreadingHTTPServer((args.host, args.port), make_handler(grabber)).serve_forever()


if __name__ == "__main__":
    main()
