"""Live-stream uploads: newest frame wins, one keep-alive connection, backend outages survive."""
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from utils.alerts import event_publisher as ep


def _server():
    got = {"bodies": [], "conns": set(), "paths": []}

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            got["bodies"].append(body)
            got["paths"].append(self.path)
            got["conns"].add(self.client_address)
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, got


def _wait(cond, secs=3.0):
    end = time.time() + secs
    while time.time() < end and not cond():
        time.sleep(0.01)
    return cond()


def test_frames_are_posted_over_one_connection(monkeypatch):
    srv, got = _server()
    monkeypatch.setattr(ep, "BACKEND_URL", f"http://127.0.0.1:{srv.server_port}")
    sender = ep._FrameSender("camA")
    for i in range(5):
        sender.submit(b"frame%d" % i)
        assert _wait(lambda n=i: b"frame%d" % n in got["bodies"])
    assert got["paths"][0] == "/api/v1/stream/frame/camA"
    assert len(got["conns"]) == 1                      # keep-alive: no reconnect per frame
    srv.shutdown()


def test_newest_frame_replaces_an_unsent_one():
    sender = ep._FrameSender.__new__(ep._FrameSender)  # no thread: inspect the slot only
    sender._slot, sender._cv = None, threading.Condition()
    sender.submit(b"old")
    sender.submit(b"new")
    assert sender._slot == b"new"


def test_backend_down_does_not_raise_or_spin(monkeypatch):
    monkeypatch.setattr(ep, "BACKEND_URL", "http://127.0.0.1:9")   # nothing listens on port 9
    sender = ep._FrameSender("camB")
    sender.submit(b"x")
    time.sleep(0.3)
    assert sender.is_alive()
