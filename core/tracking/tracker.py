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


class HumanTracker:
    def __init__(self, appearance: str = "histogram"):
        self.appearance = appearance
        self.tracker = make_deepsort(
            appearance,
            max_age=50,             # keep lost track longer (default 30)
            n_init=2,               # confirm track after 2 detections (better for low FPS)
            max_iou_distance=0.9,   # looser IoU matching for low FPS
            max_cosine_distance=0.4,# looser appearance matching
            nn_budget=100,          # appearance feature memory
        )

    def track(self, detections, frame):
        """`detections`: [([x1, y1, x2, y2], conf, cls)] — corners, as HumanDetector returns.

        DeepSORT wants (left, top, width, height); passing corners straight through made
        every tracked box ~3.5x too wide and tall.
        """
        raw = [([x1, y1, x2 - x1, y2 - y1], conf, cls) for (x1, y1, x2, y2), conf, cls in detections]
        if self.appearance == "cnn":
            return self.tracker.update_tracks(raw, frame=frame)
        embeds = [hist_embed(frame, *box) for box, _, _ in detections]
        return self.tracker.update_tracks(raw, embeds=embeds)
