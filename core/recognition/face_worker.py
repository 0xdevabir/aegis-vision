"""Face detect+encode in separate worker processes.

dlib is not safe to run next to PyTorch/MPS in one process (concurrent use segfaulted the whole
pipeline), and the only in-process fix is a shared lock that makes face work and YOLO take turns.
Workers remove both problems: dlib runs in parallel on spare CPU cores, and a dlib crash or hang
costs one worker (killed and respawned), never the camera pipeline.

Workers are plain subprocesses running this file by path, so they import only numpy, OpenCV,
face_recognition and utils/face_detect.py: no torch, no app import, ~1s start.

Wire format on the worker's stdin/stdout: 8-byte big-endian length + pickle, both directions.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import pickle
import queue
import struct
import subprocess
import sys
import threading
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[2]
logger = logging.getLogger("HumanAnalysis")


# ----------------------------------------------------------------------------- worker side

def _send(out, obj) -> None:
    data = pickle.dumps(obj, protocol=5)
    out.write(struct.pack(">Q", len(data)) + data)
    out.flush()


def _recv(inp):
    head = inp.read(8)
    if len(head) < 8:
        return None
    (n,) = struct.unpack(">Q", head)
    data = inp.read(n)
    return pickle.loads(data) if len(data) == n else None


def _serve() -> None:
    inp, out = sys.stdin.buffer, sys.stdout.buffer
    sys.stdout = sys.stderr                     # stray prints must never corrupt the pipe
    spec = importlib.util.spec_from_file_location("face_detect", _ROOT / "utils" / "face_detect.py")
    face_detect = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(face_detect)
    import face_recognition
    import numpy as np                          # noqa: F401  (pickled arrays need it importable)

    _send(out, "ready")
    while True:
        req = _recv(inp)
        if req is None:                         # parent closed the pipe or died: exit, no orphans
            return
        try:
            _send(out, ("ok", face_detect.detect_and_encode(*req, face_recognition=face_recognition)))
        except Exception as e:  # noqa: BLE001
            _send(out, ("err", f"{type(e).__name__}: {e}"))


# ----------------------------------------------------------------------------- client side

class _Worker:
    def __init__(self):
        env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1")
        self.proc = subprocess.Popen([sys.executable, str(_HERE)], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, cwd=str(_ROOT), env=env)
        self.ready = False

    def call(self, req, timeout: float, startup_timeout: float):
        """Send `req`, return the reply; raises on timeout, crash or worker-side error."""
        killer = None
        try:
            if not self.ready:
                killer = threading.Timer(startup_timeout, self.kill)
                killer.start()
                if _recv(self.proc.stdout) != "ready":
                    raise RuntimeError("face worker failed to start")
                killer.cancel()
                self.ready = True
            killer = threading.Timer(timeout, self.kill)
            killer.start()
            _send(self.proc.stdin, req)
            reply = _recv(self.proc.stdout)
            if reply is None:
                raise RuntimeError("face worker died or timed out")
            if reply[0] != "ok":
                raise RuntimeError(reply[1])
            return reply[1]
        finally:
            if killer is not None:
                killer.cancel()

    def kill(self) -> None:
        try:
            self.proc.kill()
        except Exception:  # noqa: BLE001
            pass
        for pipe in (self.proc.stdin, self.proc.stdout):
            try:
                pipe.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            self.proc.wait(timeout=2)
        except Exception:  # noqa: BLE001
            pass


class FaceWorkerPool:
    """`n` worker processes; `detect_and_encode` blocks the caller until a worker is free."""

    def __init__(self, n: int | None = None, timeout: float | None = None):
        self.n = n or int(os.getenv("FACE_WORKERS", "1"))
        self.timeout = timeout or float(os.getenv("FACE_WORKER_TIMEOUT", "10"))
        self.startup_timeout = float(os.getenv("FACE_WORKER_STARTUP_TIMEOUT", "60"))
        self._idle: queue.Queue = queue.Queue()
        for _ in range(self.n):
            self._idle.put(_Worker())

    def detect_and_encode(self, rgb, upsample, use_cnn, min_face_px, min_sharpness):
        """(encoding | None, cnn_missed); (None, False) if the worker failed (it is replaced)."""
        worker = self._idle.get()
        try:
            result = worker.call((rgb, upsample, use_cnn, min_face_px, min_sharpness),
                                 self.timeout, self.startup_timeout)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Face worker failed ({e}); respawning")
            worker.kill()
            worker = _Worker()
            result = (None, False)
        self._idle.put(worker)
        return result

    def close(self) -> None:
        while True:
            try:
                self._idle.get_nowait().kill()
            except queue.Empty:
                return


_POOL: FaceWorkerPool | None = None
_POOL_LOCK = threading.Lock()


def shared_pool() -> FaceWorkerPool:
    global _POOL
    with _POOL_LOCK:
        if _POOL is None:
            _POOL = FaceWorkerPool()
        return _POOL


if __name__ == "__main__":
    _serve()
