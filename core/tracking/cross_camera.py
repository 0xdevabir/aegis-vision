"""Cross-camera tracking of red-alert subjects by appearance.

Per-camera trackers give ids that mean nothing on another camera, and a face is only readable when
the person looks at the lens. Once someone raises a red alert (watchlist match, weapon) their
whole-body appearance is remembered here, and every running camera compares the people it sees
against it. A match flags that person as TRACKING on the other camera.

All cameras of one pipeline process (`main.py --multi`) share one tracker. An appearance match is
a lead, not an identification: similar clothes can match.
"""

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

REID_MODEL = Path(__file__).resolve().parents[2] / "models" / "person_reid_youtu_2021nov.onnx"
REID_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/person_reid_youtureid/"
            "person_reid_youtu_2021nov.onnx")

ENABLED = os.getenv("XCAM_TRACKING_ENABLED", "true").lower() == "true"
MATCH_THRESHOLD = float(os.getenv("XCAM_MATCH_THRESHOLD", "0.7"))   # cosine similarity, 0-1
TTL_SECONDS = float(os.getenv("XCAM_TTL_SECONDS", "900"))           # forget a subject unseen this long

_MEAN = np.array([0.485, 0.456, 0.406], np.float32).reshape(1, 3, 1, 1)
_STD = np.array([0.229, 0.224, 0.225], np.float32).reshape(1, 3, 1, 1)
_net = None
_net_lock = threading.Lock()


def embed(crop) -> Optional[np.ndarray]:
    """Unit-length appearance vector of a person crop (BGR). None when the model is not installed."""
    out = embed_many([crop])
    return None if out is None or not out[0].any() else out[0]


def embed_many(crops) -> Optional[np.ndarray]:
    """(n, 768) unit-length vectors for person crops (~20 ms per crop on CPU); None when the model
    is not installed. One crop per forward: OpenCV DNN returns wrong vectors for a batch of this model."""
    global _net
    with _net_lock:                                  # one net for every camera thread
        if _net is None:
            _net = cv2.dnn.readNetFromONNX(str(REID_MODEL)) if REID_MODEL.is_file() else False
        if _net is False:
            return None
        rows = []
        for crop in crops:
            _net.setInput((cv2.dnn.blobFromImage(crop, 1 / 255.0, (128, 256), swapRB=True) - _MEAN) / _STD)
            rows.append(_net.forward().flatten())
    out = np.array(rows, np.float64).reshape(len(crops), -1)
    out[~np.isfinite(out).all(axis=1)] = 0           # degenerate crops can overflow
    n = np.linalg.norm(out, axis=1, keepdims=True)
    return np.divide(out, n, out=np.zeros_like(out), where=n > 0).astype(np.float32)


@dataclass
class Target:
    """A red-alert subject being followed across cameras."""

    key: str
    label: str                      # shown on the video and the dashboard
    alert_type: str                 # what made them a target
    person_name: Optional[str]
    origin_camera: str
    origin_location: str
    last_seen: float = 0.0
    last_camera: str = ""
    gallery: list = field(default_factory=list)      # appearance vectors
    trail: list = field(default_factory=list)        # [(camera_id, location, time)], one per camera change
    direct: dict = field(default_factory=dict)       # camera_id -> last time the alert itself saw them
    sampled: float = 0.0

    def seen(self, camera_id: str, location: str, now: float) -> None:
        self.last_seen, self.last_camera = now, camera_id
        if not self.trail or self.trail[-1][0] != camera_id:
            self.trail = (self.trail + [(camera_id, location, now)])[-20:]


class CrossCameraTracker:
    """Shared by all cameras. `step` is called once per processed frame of each camera."""

    def __init__(self, embed_fn=embed, threshold: float = MATCH_THRESHOLD, ttl: float = TTL_SECONDS,
                 votes: int = 2, max_embeds: int = 2, gallery_size: int = 16, enabled: bool = ENABLED):
        self.embed_fn = embed_fn
        self.threshold = threshold
        self.ttl = ttl
        self.votes = votes
        self.max_embeds = max_embeds                 # appearance model runs per frame (~tens of ms each)
        self.gallery_size = gallery_size
        self.enabled = enabled
        self.targets: dict = {}
        self._tracks: dict = {}                      # (camera_id, track_id) -> match state
        self._lock = threading.Lock()

    def _embed(self, frame, box) -> Optional[np.ndarray]:
        fh, fw = frame.shape[:2]
        x1, y1, x2, y2 = max(0, int(box[0])), max(0, int(box[1])), min(fw, int(box[2])), min(fh, int(box[3]))
        if x2 - x1 < 24 or y2 - y1 < 64:             # too small to tell people apart
            return None
        return self.embed_fn(frame[y1:y2, x1:x2])

    def _best(self, emb, skip: set):
        best, best_sim = None, 0.0
        for key, t in self.targets.items():
            if key in skip or not t.gallery:
                continue
            sim = float(np.max(np.stack(t.gallery) @ emb))
            if sim > best_sim:
                best, best_sim = key, sim
        return best, best_sim

    def step(self, camera_id: str, location: str, now: float, frame, subjects: list, others: list) -> dict:
        """One frame of one camera.

        `subjects`: [(track_id, box, key, label, alert_type, person_name)] — people with a live red alert.
        `others`: [(track_id, box)] — everyone else in view.
        Returns {track_id: Target} for the others that match a subject seen earlier or elsewhere.
        """
        if not self.enabled:
            return {}
        with self._lock:
            for key in [k for k, t in self.targets.items() if now - t.last_seen > self.ttl]:
                del self.targets[key]
            budget = self.max_embeds

            for track_id, box, key, label, alert_type, person_name in subjects:
                t = self.targets.get(key)
                if t is None:
                    t = self.targets[key] = Target(key, label, alert_type, person_name, camera_id, location)
                t.seen(camera_id, location, now)
                t.direct[camera_id] = now
                if budget and now - t.sampled >= 1.5:
                    emb = self._embed(frame, box)
                    if emb is not None:
                        budget -= 1
                        t.sampled = now
                        t.gallery = (t.gallery + [emb])[-self.gallery_size:]

            live = {(camera_id, track_id) for track_id, _ in others}
            for k in [k for k in self._tracks if k[0] == camera_id and k not in live]:
                del self._tracks[k]
            # Someone the alert itself sees on this camera right now is not also another track here.
            here = {key for key, t in self.targets.items() if now - t.direct.get(camera_id, -1e9) < 2.0}

            found = {}
            for track_id, box in sorted(others, key=lambda o: -(o[1][2] - o[1][0]) * (o[1][3] - o[1][1])):
                st = self._tracks.setdefault((camera_id, track_id), {"target": None, "votes": {}, "fails": 0, "next": 0.0})
                if st["target"] not in self.targets:
                    st["target"] = None
                if budget and now >= st["next"] and any(t.gallery for k, t in self.targets.items() if k not in here):
                    emb = self._embed(frame, box)
                    if emb is not None:
                        budget -= 1
                        key, sim = self._best(emb, here)
                        if key is not None and sim >= self.threshold:
                            if key == st["target"]:
                                st["fails"] = 0
                            else:
                                st["votes"][key] = st["votes"].get(key, 0) + 1
                                if st["votes"][key] >= self.votes:      # one lookalike frame is not a match
                                    st.update(target=key, votes={}, fails=0)
                        elif st["target"]:
                            st["fails"] += 1
                            if st["fails"] >= 2:                         # the tracker id moved to someone else
                                st.update(target=None, votes={}, fails=0)
                        # Re-check a followed person now and then; keep trying the others more often.
                        st["next"] = now + (3.0 if st["target"] else 1.0)
                if st["target"] and st["target"] not in here:
                    t = self.targets[st["target"]]
                    t.seen(camera_id, location, now)
                    found[track_id] = t
            return found


_shared: Optional[CrossCameraTracker] = None
_shared_lock = threading.Lock()


def shared_tracker() -> CrossCameraTracker:
    """The tracker every camera of this process reports to."""
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = CrossCameraTracker()
        return _shared
