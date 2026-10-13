from core.detectors.device import lock_for, read_boxes

import numpy as np
from ultralytics import YOLO
from core.tracking.tracker import hist_embed, make_deepsort


VEHICLE_CLASSES = {
    2: "car", 3: "motorcycle", 5: "bus", 7: "truck",
}


class VehicleDetector:
    def __init__(self, model_path: str, conf_threshold: float = 0.5, device: str = "cpu"):
        self.model = YOLO(model_path)
        self.conf_threshold = conf_threshold
        self.device = device
        self._lock = lock_for(device)
        self.vehicle_classes = list(VEHICLE_CLASSES.keys())

    def detect(self, frame: np.ndarray):
        with self._lock:
            results = self.model(frame, conf=self.conf_threshold, classes=self.vehicle_classes, verbose=False, device=self.device)
            boxes = read_boxes(results)
        return [{
            "bbox": (x1, y1, x2, y2),
            "score": conf,
            "class_id": cls_id,
            "class_name": VEHICLE_CLASSES.get(cls_id, "vehicle"),
        } for x1, y1, x2, y2, conf, cls_id in boxes]


class VehicleTracker:
    def __init__(self, appearance: str = "histogram"):
        self.appearance = appearance
        self.tracker = make_deepsort(
            appearance,
            max_age=30, n_init=3, max_iou_distance=0.7,
            max_cosine_distance=0.3, nn_budget=50,
        )

    def track(self, detections, frame):
        deepsort_dets = []
        for v in detections:
            x1, y1, x2, y2 = v["bbox"]
            w, h = x2 - x1, y2 - y1
            deepsort_dets.append(([x1, y1, w, h], v["score"], v["class_id"]))
        if self.appearance == "cnn":
            return self.tracker.update_tracks(deepsort_dets, frame=frame)
        embeds = [hist_embed(frame, *v["bbox"]) for v in detections]
        return self.tracker.update_tracks(deepsort_dets, embeds=embeds)
