"""Fall *suspicion* from pose + time. A person lying down is not automatically a fall:
we require an upright period followed by sustained horizontal posture, and the alert
is worded "suspected" for human check."""

import math
from typing import Optional, Tuple

import numpy as np  # noqa: F401  (kept for callers passing numpy scalars)


def _mid(kp, a, b) -> Optional[Tuple[float, float]]:
    pa, pb = kp.get(a), kp.get(b)
    if pa and pb:
        return (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
    return pa[:2] if pa else (pb[:2] if pb else None)


def torso_angle_from_vertical(kp) -> Optional[float]:
    """Degrees between the shoulder→hip axis and vertical (0 upright, 90 lying)."""
    s = _mid(kp, "left_shoulder", "right_shoulder")
    h = _mid(kp, "left_hip", "right_hip")
    if not s or not h:
        return None
    dx, dy = h[0] - s[0], h[1] - s[1]
    if math.hypot(dx, dy) < 1e-6:
        return None
    return math.degrees(math.atan2(abs(dx), abs(dy)))


def posture(kp, bbox) -> Optional[str]:
    """'upright' | 'horizontal' | None (unknown)."""
    ang = torso_angle_from_vertical(kp)
    x1, y1, x2, y2 = bbox
    w, h = max(1, x2 - x1), max(1, y2 - y1)
    if ang is None:
        return None
    if ang >= 60 and w / h >= 1.0:
        return "horizontal"
    if ang <= 35 and h / w >= 1.2:
        return "upright"
    return None


class FallDetector:
    def __init__(self, upright_memory: float = 4.0, lie_seconds: float = 2.0):
        self.upright_memory = upright_memory
        self.lie_seconds = lie_seconds
        self._last_upright = {}
        self._lying_since = {}
        self._reported = set()

    def update(self, track_id: int, kp, bbox, now: float) -> bool:
        """True exactly once per fall episode."""
        state = posture(kp, bbox)
        if state == "upright":
            self._last_upright[track_id] = now
            self._lying_since.pop(track_id, None)
            self._reported.discard(track_id)
            return False
        if state == "horizontal":
            self._lying_since.setdefault(track_id, now)
            recently_upright = now - self._last_upright.get(track_id, -1e9) <= self.upright_memory + self.lie_seconds
            if (track_id not in self._reported and recently_upright
                    and now - self._lying_since[track_id] >= self.lie_seconds):
                self._reported.add(track_id)
                return True
        return False

    def prune(self, live_ids) -> None:
        for d in (self._last_upright, self._lying_since):
            for t in [t for t in d if t not in live_ids]:
                del d[t]
        self._reported &= set(live_ids)
