from core.detectors.device import lock_for, read_boxes

import numpy as np
from ultralytics import YOLO


class HumanDetector:
    def __init__(self, model_path: str, conf_threshold: float = 0.5, device: str = "cpu",
                 imgsz: int | None = None):
        self.model = YOLO(model_path)
        self.imgsz = imgsz
        self.conf_threshold = conf_threshold
        self.device = device
        self._lock = lock_for(device)   # one model instance is shared by all cameras

    def detect(self, frame: np.ndarray):
        with self._lock:
            results = self.model(frame, conf=self.conf_threshold, classes=[0], verbose=False, device=self.device,
                                 **({"imgsz": self.imgsz} if self.imgsz else {}))
            boxes = read_boxes(results)                  # tensor reads are GPU work: keep them in the lock
        return [([x1, y1, x2, y2], conf, 0) for x1, y1, x2, y2, conf, _ in boxes]
