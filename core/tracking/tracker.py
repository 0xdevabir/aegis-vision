import cv2
import numpy as np
from deep_sort_realtime.deepsort_tracker import DeepSort


def hist_embed(frame, x1, y1, x2, y2) -> np.ndarray:
    """Cheap appearance signature: HSV colour histogram of the box (~1 ms vs ~120 ms for a CNN)."""
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = max(0, int(x1)), max(0, int(y1)), min(w, int(x2)), min(h, int(y2))
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return np.ones(128, dtype=np.float32) / np.sqrt(128)
    hsv = cv2.cvtColor(cv2.resize(crop, (32, 64)), cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 4, 4], [0, 180, 0, 256, 0, 256]).flatten()
    n = np.linalg.norm(hist)
    return (hist / n if n else np.ones(128) / np.sqrt(128)).astype(np.float32)


def make_deepsort(appearance: str, **kw) -> DeepSort:
    """'histogram' (fast, default) or 'cnn' (MobileNet embeddings, more robust, much slower on CPU)."""
    if appearance == "cnn":
        # embedder_gpu=True measured ~3x SLOWER than CPU on Apple silicon (1240 vs 366 ms/frame)
        return DeepSort(embedder_gpu=False, **kw)
    return DeepSort(embedder=None, **kw)


def reid_embeds(frame, boxes) -> list:
    """Person re-identification vectors (models/person_reid_youtu_2021nov.onnx) for corner boxes.
    Far better than colour histograms at telling apart people in similar clothes, so ids survive
    people crossing / overlapping."""
    from core.tracking.cross_camera import embed_many
    h, w = frame.shape[:2]
    out = np.tile(np.float32(1 / np.sqrt(768)), (len(boxes), 768))   # placeholder for unusable crops
    crops, rows = [], []
    for i, (x1, y1, x2, y2) in enumerate(boxes):
        x1, y1, x2, y2 = max(0, int(x1)), max(0, int(y1)), min(w, int(x2)), min(h, int(y2))
        if x2 - x1 >= 8 and y2 - y1 >= 16:
            crops.append(frame[y1:y2, x1:x2])
            rows.append(i)
    if crops:
        vecs = embed_many(crops)
        for i, v in zip(rows, vecs):
            if v.any():                  # DeepSORT divides by the norm: never hand it a zero vector
                out[i] = v
    return list(out)


class HumanTracker:
    def __init__(self, appearance: str = "histogram", algorithm: str = "deepsort", **overrides):
        # 'reid' measured ~290 ms/frame on CPU with 2-5 people and more broken-up ids: GPU only.
        if appearance == "reid":
            from core.tracking.cross_camera import REID_MODEL
            if not REID_MODEL.is_file():
                appearance = "histogram"     # a track's gallery can't mix the two kinds of vector
        self.appearance = appearance
        reid = appearance == "reid"
        params = dict(
            max_age=50,             # keep lost track longer (default 30)
            n_init=2,               # confirm track after 2 detections (better for low FPS)
            # IoU gate: 0.9 let a coasting track jump onto a different, barely overlapping person
            # (0.7 halved likely id switches on office recordings, 6 → 3)
            max_iou_distance=0.7,
            # ReID vectors of one person sit well under 0.3 apart; histograms need more slack
            max_cosine_distance=0.3 if reid else 0.4,
            nn_budget=100,          # appearance feature memory
        )
        params.update(overrides)
        self.tracker, self._bytetrack = make_tracker(algorithm, appearance, **params)

    def track(self, detections, frame):
        """`detections`: [([x1, y1, x2, y2], conf, cls)] — corners, as HumanDetector returns.

        DeepSORT wants (left, top, width, height); passing corners straight through made
        every tracked box ~3.5x too wide and tall.
        """
        if self._bytetrack:
            return self.tracker.update([d[0] for d in detections], [d[1] for d in detections],
                                       [d[2] for d in detections])
        raw = [([x1, y1, x2 - x1, y2 - y1], conf, cls) for (x1, y1, x2, y2), conf, cls in detections]
        if self.appearance == "cnn":
            return self.tracker.update_tracks(raw, frame=frame)
        if self.appearance == "reid":
            embeds = reid_embeds(frame, [box for box, _, _ in detections])
        else:
            embeds = [hist_embed(frame, *box) for box, _, _ in detections]
        return self.tracker.update_tracks(raw, embeds=embeds)


class _Dets:
    """The slice of ultralytics `Boxes` that BYTETracker.update reads (numpy only)."""

    def __init__(self, xyxy, conf, cls):
        self.xyxy = np.asarray(xyxy, dtype=np.float32).reshape(-1, 4)
        self.conf = np.asarray(conf, dtype=np.float32)
        self.cls = np.asarray(cls, dtype=np.float32)

    @property
    def xywh(self):                 # centre-x, centre-y, width, height
        b = self.xyxy
        return np.stack([(b[:, 0] + b[:, 2]) / 2, (b[:, 1] + b[:, 3]) / 2,
                         b[:, 2] - b[:, 0], b[:, 3] - b[:, 1]], axis=1)

    def __len__(self):
        return len(self.conf)

    def __getitem__(self, idx):
        return _Dets(self.xyxy[idx], self.conf[idx], self.cls[idx])


class ByteTrackResult:
    """One ByteTrack output with the DeepSORT track surface the stages use."""

    def __init__(self, track_id, ltrb, score, cls):
        self.track_id = str(track_id)       # DeepSORT ids are strings too
        self._ltrb = ltrb
        self.det_conf = score
        self.det_class = cls

    def is_confirmed(self) -> bool:
        return True                          # ByteTrack only returns activated tracks

    def to_ltrb(self):
        return self._ltrb


class ByteTrackBackend:
    """ByteTrack (ultralytics): matches on motion + IoU and re-uses low-score detections,
    so people keep their id through partial occlusion. No appearance model, so no per-frame
    embedding cost. `max_age` is in processed frames, like DeepSORT's.
    """

    def __init__(self, max_age: int = 50, high_thresh: float = 0.5, low_thresh: float = 0.1,
                 match_thresh: float = 0.8):
        from types import SimpleNamespace
        from ultralytics.trackers.byte_tracker import BYTETracker

        class _Tracker(BYTETracker):
            # The stock tracker zeroes a process-wide id counter on construction. With one
            # tracker per camera that would hand a live track's id to a new person.
            @staticmethod
            def reset_id():
                pass

        self._tracker = _Tracker(SimpleNamespace(
            track_high_thresh=high_thresh, track_low_thresh=low_thresh,
            new_track_thresh=high_thresh, track_buffer=max_age,
            match_thresh=match_thresh, fuse_score=True,
        ), frame_rate=30)

    def update(self, xyxy, conf, cls):
        rows = self._tracker.update(_Dets(xyxy, conf, cls))
        return [ByteTrackResult(int(r[4]), r[:4].tolist(), float(r[5]), int(r[6])) for r in rows]


def make_tracker(algorithm: str, appearance: str, **deepsort_kw):
    """'deepsort' (default) or 'bytetrack'. Returns (backend, is_bytetrack)."""
    if algorithm == "bytetrack":
        return ByteTrackBackend(max_age=deepsort_kw.get("max_age", 50)), True
    if algorithm != "deepsort":
        raise ValueError(f"Unknown tracking algorithm: {algorithm} (use deepsort or bytetrack)")
    return make_deepsort(appearance, **deepsort_kw), False
