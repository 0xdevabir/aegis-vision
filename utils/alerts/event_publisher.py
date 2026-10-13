"""Push alerts and events from the CV pipeline to the FastAPI backend."""

import os
import logging
import threading
import time
from typing import Optional

logger = logging.getLogger("HumanAnalysis")

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")
EVENTS_ENABLED = os.getenv("PIPELINE_EVENTS_ENABLED", "true").lower() == "true"
AUTO_ALERTS_ENABLED = os.getenv("AUTO_ALERTS_ENABLED", "true").lower() == "true"


def set_auto_alerts_enabled(enabled: bool) -> None:
    global AUTO_ALERTS_ENABLED
    AUTO_ALERTS_ENABLED = bool(enabled)


def _headers() -> dict:
    return {"X-Internal-Key": INTERNAL_API_KEY, "Content-Type": "application/json"}


def _post_async(path: str, payload: dict) -> None:
    def _send():
        try:
            import httpx

            resp = httpx.post(
                f"{BACKEND_URL}{path}",
                json=payload,
                headers=_headers(),
                timeout=5.0,
            )
            if resp.status_code >= 400:
                logger.warning(f"Backend {path} returned {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"Backend publish failed ({path}): {e}")

    threading.Thread(target=_send, daemon=True).start()


def dispatch_alert(
    alert_type: str,
    severity: str = "critical",
    camera_location: Optional[str] = None,
    camera_id: Optional[str] = None,
    track_id: Optional[int] = None,
    person_name: Optional[str] = None,
    plate_number: Optional[str] = None,
    message: Optional[str] = None,
    camera_name: Optional[str] = None,
    camera_lat: Optional[float] = None,
    camera_lng: Optional[float] = None,
    zone: Optional[str] = None,
    confidence: Optional[float] = None,
) -> None:
    """One call → DB + audit + WebSocket + webhooks + dashboard (all cameras)."""
    if not AUTO_ALERTS_ENABLED:
        return
    _post_async(
        "/api/v1/alerts/dispatch",
        {
            "alert_type": alert_type,
            "severity": severity,
            "camera_location": camera_location,
            "camera_id": camera_id,
            "track_id": track_id,
            "person_name": person_name,
            "plate_number": plate_number,
            "message": message,
            "camera_name": camera_name,
            "camera_lat": camera_lat,
            "camera_lng": camera_lng,
            "zone": zone,
            "confidence": confidence,
        },
    )


def publish_live_event(
    event_type: str,
    severity: str = "info",
    camera_location: Optional[str] = None,
    camera_id: Optional[str] = None,
    track_id: Optional[int] = None,
    person_name: Optional[str] = None,
    message: Optional[str] = None,
) -> None:
    if not EVENTS_ENABLED:
        return
    _post_async(
        "/api/v1/events/internal",
        {
            "event_type": event_type,
            "severity": severity,
            "camera_location": camera_location,
            "camera_id": camera_id,
            "track_id": track_id,
            "person_name": person_name,
            "message": message,
        },
    )


_STREAM_ENABLED = os.getenv("PIPELINE_STREAM_ENABLED", "true").lower() == "true"


class _FrameSender(threading.Thread):
    """Uploads one camera's newest JPEG over a single keep-alive connection.

    The camera loop only drops its latest frame into a slot (never blocks, never spawns a thread,
    never skips a frame just because the previous upload was still in flight); this thread sends
    whatever is newest as fast as the backend accepts it. Plain http.client keeps the work per
    frame to a couple of syscalls, which matters here: the pipeline process is GIL-bound and a
    thread that needs the GIL many times per upload (httpx did) is starved by YOLO's Python code.
    """

    def __init__(self, camera_id: str):
        super().__init__(name=f"frame-sender-{camera_id}", daemon=True)
        self.camera_id = camera_id
        self._slot = None
        self._cv = threading.Condition()
        self._last_error_log = 0.0
        self.start()

    def submit(self, jpeg: bytes) -> None:
        with self._cv:
            self._slot = jpeg                       # replaces an unsent older frame: newest wins
            self._cv.notify()

    def _connect(self):
        import http.client
        from urllib.parse import urlsplit

        u = urlsplit(BACKEND_URL)
        cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
        return cls(u.hostname, u.port or (443 if u.scheme == "https" else 80), timeout=3.0)

    def run(self) -> None:
        conn = None
        path = f"/api/v1/stream/frame/{self.camera_id}"
        headers = {"X-Internal-Key": INTERNAL_API_KEY, "Content-Type": "image/jpeg"}
        while True:
            with self._cv:
                while self._slot is None:
                    self._cv.wait()
                jpeg, self._slot = self._slot, None
            try:
                if conn is None:
                    conn = self._connect()
                conn.request("POST", path, body=jpeg, headers=headers)
                conn.getresponse().read()           # drain so the connection can be reused
            except Exception as e:  # noqa: BLE001
                if conn is not None:
                    conn.close()
                conn = None
                now = time.monotonic()
                if now - self._last_error_log > 10:
                    self._last_error_log = now
                    logger.error(f"publish_frame failed for {self.camera_id}: {e}")
                time.sleep(0.5)                     # backend down: don't spin


_senders: dict = {}
_senders_lock = threading.Lock()


def publish_frame(camera_id: str, jpeg_bytes: bytes) -> None:
    """Hand the latest annotated JPEG frame for `camera_id` to its sender; returns immediately."""
    if not _STREAM_ENABLED:
        return
    sender = _senders.get(camera_id)
    if sender is None:
        with _senders_lock:
            sender = _senders.setdefault(camera_id, _FrameSender(camera_id))
    sender.submit(jpeg_bytes)


_last_clip: dict = {}
_CLIP_COOLDOWN = float(os.getenv("CLIP_COOLDOWN_SECONDS", "15"))


def publish_event_clip(
    camera_id: str,
    jpeg_bytes: bytes,
    *,
    camera_location: str = "",
    alert_type: str = "EVENT",
) -> None:
    """Upload an event-triggered still to the recordings timeline (VMS slice)."""
    now = __import__("time").time()
    if now - _last_clip.get(camera_id, 0) < _CLIP_COOLDOWN:
        return
    _last_clip[camera_id] = now

    def _send():
        try:
            import httpx
            from datetime import datetime

            files = {"file": ("event.jpg", jpeg_bytes, "image/jpeg")}
            data = {
                "camera_id": camera_id,
                "camera_location": camera_location or "",
                "trigger": "event",
                "alert_type": alert_type,
                "started_at": datetime.utcnow().isoformat(),
                "frame_count": "1",
            }
            httpx.post(
                f"{BACKEND_URL}/api/v1/recordings/ingest",
                data=data,
                files=files,
                headers={"X-Internal-Key": INTERNAL_API_KEY},
                timeout=8.0,
            )
        except Exception as e:
            logger.warning(f"Clip ingest failed: {e}")

    threading.Thread(target=_send, daemon=True).start()


def publish_heartbeat(
    camera_id: str,
    camera_location: str = "",
    fps: Optional[float] = None,
    threat_score: Optional[int] = None,
    frame_number: Optional[int] = None,
    analytics: Optional[dict] = None,
) -> None:
    if not EVENTS_ENABLED:
        return
    _post_async(
        "/api/v1/system/heartbeat",
        {
            "camera_id": camera_id,
            "camera_location": camera_location,
            "fps": fps,
            "threat_score": threat_score,
            "frame_number": frame_number,
            "analytics": analytics,
        },
    )

