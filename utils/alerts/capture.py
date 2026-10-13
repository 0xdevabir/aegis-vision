"""Red-alert capture: a zoomed, full-quality still of the subject every few seconds.

While a critical alert is live for a subject, the pipeline crops that subject out of the raw
frame (not the downscaled dashboard stream), enlarges it and uploads it to the capture basket.
"""

import os
from typing import Optional, Sequence

import cv2

from utils.alerts.event_publisher import publish_capture

CAPTURE_ENABLED = os.getenv("CAPTURE_ENABLED", "true").lower() == "true"
CAPTURE_INTERVAL = float(os.getenv("CAPTURE_INTERVAL_SECONDS", "5"))
CAPTURE_MIN_SIDE = int(os.getenv("CAPTURE_MIN_SIDE", "720"))
CAPTURE_QUALITY = int(os.getenv("CAPTURE_QUALITY", "95"))


def zoom_crop(frame, bbox: Sequence[float], pad: float = 0.2,
              min_side: int = CAPTURE_MIN_SIDE, max_zoom: float = 4.0):
    """Crop `bbox` (x1, y1, x2, y2) with a margin and enlarge it so its long side reaches `min_side`.

    Returns (image, (x1, y1, x2, y2) of the padded box) or None for an empty box.
    """
    fh, fw = frame.shape[:2]
    x1, y1, x2, y2 = map(float, bbox)
    mx, my = (x2 - x1) * pad, (y2 - y1) * pad
    x1, y1 = max(0, int(x1 - mx)), max(0, int(y1 - my))
    x2, y2 = min(fw, int(x2 + mx)), min(fh, int(y2 + my))
    if x2 - x1 < 8 or y2 - y1 < 8:
        return None
    crop = frame[y1:y2, x1:x2]
    zoom = min(max_zoom, min_side / max(x2 - x1, y2 - y1))
    if zoom > 1.05:
        crop = cv2.resize(crop, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_LANCZOS4)
    else:
        crop = crop.copy()
    return crop, (x1, y1, x2, y2)


class AlertCapturer:
    """One capture per subject per `interval` seconds."""

    def __init__(self, interval: float = CAPTURE_INTERVAL, enabled: bool = CAPTURE_ENABLED):
        self.interval = interval
        self.enabled = enabled
        self._last: dict = {}

    def _due(self, key: str, now: float) -> bool:
        if now - self._last.get(key, 0) < self.interval:
            return False
        if len(self._last) > 256:                    # tracks that left the scene long ago
            self._last = {k: t for k, t in self._last.items() if now - t < 10 * self.interval}
        self._last[key] = now
        return True

    def capture(self, key: str, now: float, frame, bbox, *, camera_id: str, alert_type: str,
                camera_location: str = "", camera_name: str = "",
                camera_lat: Optional[float] = None, camera_lng: Optional[float] = None,
                track_id: Optional[int] = None, person_name: Optional[str] = None,
                confidence: Optional[float] = None) -> bool:
        """Upload a zoomed still of `bbox` if this subject is due. True when one was sent."""
        if not self.enabled or bbox is None or not self._due(f"{camera_id}:{key}", now):
            return False
        result = zoom_crop(frame, bbox)
        if result is None:
            return False
        image, (x1, y1, x2, y2) = result
        ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, CAPTURE_QUALITY])
        if not ok:
            return False
        fh, fw = frame.shape[:2]
        publish_capture(camera_id, buf.tobytes(), {
            "alert_type": alert_type,
            "camera_location": camera_location,
            "camera_name": camera_name,
            "camera_lat": camera_lat,
            "camera_lng": camera_lng,
            "track_id": track_id,
            "person_name": person_name,
            "confidence": confidence,
            # where the subject sits in the frame (0-1), so the dashboard can point at it
            "bbox": f"{x1 / fw:.4f},{y1 / fh:.4f},{(x2 - x1) / fw:.4f},{(y2 - y1) / fh:.4f}",
            "source_width": x2 - x1,
            "source_height": y2 - y1,
        })
        return True
