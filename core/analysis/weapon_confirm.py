"""Associate weapon detections with person tracks and confirm over time.

A single frame is never treated as certain: a weapon alert fires only when the
same track (or the unassigned bucket) has a weapon hit in at least `min_hits`
of the last `window` processed frames.
"""

from collections import defaultdict, deque
from typing import Iterable, Optional

UNASSIGNED = -1


def _overlap_ratio(weapon_bbox, person_bbox) -> float:
    """Fraction of the weapon box that lies inside the person box."""
    wx1, wy1, wx2, wy2 = weapon_bbox
    px1, py1, px2, py2 = person_bbox
    iw = min(wx2, px2) - max(wx1, px1)
    ih = min(wy2, py2) - max(wy1, py1)
    area = max(1, (wx2 - wx1) * (wy2 - wy1))
    return max(0, iw) * max(0, ih) / area


def associate(weapon_detections: Iterable[dict], tracks, min_overlap: float = 0.3) -> dict:
    """Map track_id -> best weapon detection. Unmatched weapons go to UNASSIGNED."""
    boxes = {}
    for t in tracks:
        if t.is_confirmed():
            boxes[t.track_id] = tuple(map(int, t.to_ltrb()))

    out: dict = {}
    for w in weapon_detections:
        best_id: Optional[int] = None
        best = min_overlap
        for tid, pb in boxes.items():
            r = _overlap_ratio(w["bbox"], pb)
            if r >= best:
                best, best_id = r, tid
        key = UNASSIGNED if best_id is None else best_id
        if key not in out or w["score"] > out[key]["score"]:
            out[key] = w
    return out


class WeaponConfirmer:
    def __init__(self, window: int = 5, min_hits: int = 3):
        self.window = window
        self.min_hits = min_hits
        self._hist = defaultdict(lambda: deque(maxlen=window))

    def update(self, assigned: dict) -> set:
        """Feed one processed frame; return keys confirmed on this frame."""
        for key in set(self._hist) | set(assigned):
            self._hist[key].append(key in assigned)
        confirmed = {
            k for k, h in self._hist.items()
            if k in assigned and sum(h) >= self.min_hits
        }
        for k in [k for k, h in self._hist.items() if not any(h)]:
            del self._hist[k]
        return confirmed
