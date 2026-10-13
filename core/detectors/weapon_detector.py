from core.detectors.device import lock_for, read_boxes

import numpy as np
from ultralytics import YOLO


class WeaponDetector:
    def __init__(self, model_path: str, conf_threshold: float = 0.4, device: str = "cpu"):
        self.model = YOLO(model_path)
        self.conf_threshold = conf_threshold
        self.device = device
        self._lock = lock_for(device)

    def detect(self, frame: np.ndarray):
        with self._lock:
            results = self.model(frame, conf=self.conf_threshold, verbose=False, device=self.device)
            boxes = read_boxes(results)
        return [{"bbox": (x1, y1, x2, y2), "score": conf, "class_id": cls_id}
                for x1, y1, x2, y2, conf, cls_id in boxes]
