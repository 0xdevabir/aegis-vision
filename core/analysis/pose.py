"""Multi-person pose via ultralytics YOLO-pose (replaces MediaPipe).

One forward pass per frame returns every person's 17 COCO keypoints, so there is no
per-person crop. Works with numpy 2, shares the pipeline's device, and drops the
mediapipe / protobuf<4 / opencv-contrib dependency chain.
"""

import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("HumanAnalysis")

KEYPOINT_NAMES = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]

Pose = Dict[str, Tuple[float, float, float]]       # name → (x, y, confidence)


def assign_poses(poses: List[dict], tracks, min_inside: float = 0.5) -> Dict[int, dict]:
    """Match poses to confirmed, currently-seen tracks one-to-one, best box IoU first.

    A pose needs at least `min_inside` of its box inside the track box. One-to-one matters when
    people overlap (a fight): a large box contains both skeletons, and handing the same skeleton
    to two tracks, or one person's to the other, makes their motion meaningless. Coasting tracks
    (not matched to a detection this frame) sit at a predicted spot and get no pose.
    """
    pairs = []
    for t in tracks:
        if not t.is_confirmed() or getattr(t, "time_since_update", 0) > 0:
            continue
        tx1, ty1, tx2, ty2 = map(int, t.to_ltrb())
        for j, p in enumerate(poses):
            px1, py1, px2, py2 = p["bbox"]
            inter = max(0, min(tx2, px2) - max(tx1, px1)) * max(0, min(ty2, py2) - max(ty1, py1))
            area = max(1, (px2 - px1) * (py2 - py1))
            if inter / area > min_inside:
                union = area + (tx2 - tx1) * (ty2 - ty1) - inter
                pairs.append((inter / max(1, union), t.track_id, j))
    out: Dict[int, dict] = {}
    used = set()
    for _, tid, j in sorted(pairs, key=lambda x: -x[0]):
        if tid not in out and j not in used:
            out[tid] = poses[j]
            used.add(j)
    return out


class PoseAnalyzer:
    """Disabled (returns []) if the model can't be loaded; never crashes the pipeline."""

    def __init__(self, model_path: Optional[str] = None, device: str = "cpu",
                 conf: float = 0.4, min_kpt_conf: float = 0.3,
                 auto_download: bool = False, imgsz: Optional[int] = None):
        self.device = device
        self.imgsz = imgsz
        self.conf = conf
        self.min_kpt_conf = min_kpt_conf
        from core.detectors.device import lock_for   # lazy: keeps this module torch-free
        self._lock = lock_for(device)
        self.model = None
        if model_path:
            try:
                import os

                from ultralytics import YOLO
                if auto_download and not os.path.exists(model_path):
                    # Official Ultralytics asset; saved at model_path (models/), not the cwd.
                    from ultralytics.utils.downloads import attempt_download_asset
                    os.makedirs(os.path.dirname(model_path) or ".", exist_ok=True)
                    attempt_download_asset(model_path)
                self.model = YOLO(model_path)
            except Exception as e:
                logger.warning(f"PoseAnalyzer disabled: {e}")

    @property
    def enabled(self) -> bool:
        return self.model is not None

    def detect(self, frame) -> List[dict]:
        if self.model is None:
            return []
        with self._lock:
            results = self.model(frame, conf=self.conf, verbose=False, device=self.device,
                                 **({"imgsz": self.imgsz} if self.imgsz else {}))
            # Copy to numpy inside the lock: tensor reads are Metal work and must not overlap another
            # thread's inference (see core.detectors.device.read_boxes).
            raw = [(r.keypoints.data.cpu().numpy(), r.boxes.xyxy.cpu().numpy())      # kp: (n, 17, 3)
                   for r in results if r.keypoints is not None and r.boxes is not None]
        poses = []
        for kp, boxes in raw:
            for box, pts in zip(boxes, kp):
                pose: Pose = {
                    name: (float(x), float(y), float(c))
                    for name, (x, y, c) in zip(KEYPOINT_NAMES, pts)
                    if c >= self.min_kpt_conf
                }
                poses.append({"bbox": tuple(int(v) for v in box), "kpts": pose})
        return poses
