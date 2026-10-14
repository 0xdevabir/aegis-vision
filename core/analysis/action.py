"""Learned action recognition from pose sequences (ST-GCN, NTU RGB+D 60).

The pose stage already gives every person 17 COCO keypoints. Here the last few seconds of a
person's keypoints, plus those of the nearest other person (NTU's two-person interactions:
punching, kicking, pushing), go through MMAction2's pretrained ST-GCN, exported to ONNX by
`scripts/export_action_model.py` and run with OpenCV DNN, so no torch / MPS work in this step.

Only a few classes raise anything (`ALERT_ACTIONS`); a classification is a lead for a human to
check, like the rule-based reasons in core.analysis.behavior.
"""

import logging
import threading
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

from core.analysis.pose import KEYPOINT_NAMES

logger = logging.getLogger("HumanAnalysis")

ACTION_MODEL = Path(__file__).resolve().parents[2] / "models" / "action_stgcn_ntu60.onnx"
CLIP_LEN, NUM_JOINTS, NUM_PERSON = 100, 17, 2
SOURCE_FPS = 30.0                    # NTU RGB+D frame rate the model was trained at

NTU60_LABELS = [
    "drink water", "eat meal/snack", "brushing teeth", "brushing hair", "drop", "pickup", "throw",
    "sitting down", "standing up", "clapping", "reading", "writing", "tear up paper", "wear jacket",
    "take off jacket", "wear a shoe", "take off a shoe", "wear on glasses", "take off glasses",
    "put on a hat/cap", "take off a hat/cap", "cheer up", "hand waving", "kicking something",
    "reach into pocket", "hopping", "jump up", "make a phone call", "playing with phone/tablet",
    "typing on a keyboard", "pointing to something", "taking a selfie", "check time (from watch)",
    "rub two hands together", "nod head/bow", "shake head", "wipe face", "salute",
    "put the palms together", "cross hands in front", "sneeze/cough", "staggering", "falling",
    "touch head (headache)", "touch chest (stomachache/heart pain)", "touch back (backache)",
    "touch neck (neckache)", "nausea or vomiting", "use a fan/feeling warm",
    "punching/slapping other person", "kicking other person", "pushing other person",
    "pat on back of other person", "point finger at other person", "hugging other person",
    "giving something to other person", "touch other person's pocket", "handshaking",
    "walking towards each other", "walking apart from each other",
]

# NTU class index → reason reported on the track. Everything else is ignored.
# Not fighting (49 punching, 50 kicking, 51 pushing): on real CCTV fights (fight-detection-surv-dataset)
# it flagged 0/30, and on staged indoor fights (airtlab) it flagged fights and normal clips alike.
ALERT_ACTIONS = {
    41: "staggering",
    42: "falling",
}


def _to_array(kpts: dict) -> Optional[np.ndarray]:
    """Pose dict → (17, 3) x, y, score. Joints the pose model dropped sit on the body centre with
    score 0 (NTU's HRNet keypoints are never missing, so zeros at the frame origin would mislead)."""
    pts = [kpts.get(name) for name in KEYPOINT_NAMES]
    seen = [p for p in pts if p]
    if len(seen) < 5:
        return None
    cx = sum(p[0] for p in seen) / len(seen)
    cy = sum(p[1] for p in seen) / len(seen)
    return np.array([p if p else (cx, cy, 0.0) for p in pts], np.float32)


class ActionRecognizer:
    """Per-camera: keeps a short keypoint history and classifies each person about once a second.

    A classification costs ~150 ms on CPU, so it runs on one background thread (OpenCV releases
    the GIL) and the video never waits for it; with many people each is simply visited less often.
    Disabled (classifies nothing) if the ONNX file is missing; never crashes the pipeline.
    """

    def __init__(self, model_path: Path = ACTION_MODEL, window_seconds: float = 3.0,
                 every_seconds: float = 1.0, min_confidence: float = 0.6):
        self.window = window_seconds
        self.every = every_seconds
        self.min_confidence = min_confidence
        self._history: deque = deque()            # (t, {track_id: (17, 3) pixels})
        self._last_run: Dict[int, float] = {}
        self._results: Dict[int, Tuple[str, str, float]] = {}   # tid → (reason, label, score)
        self._lock = threading.Lock()             # _results is written by the worker
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="action")
        self._pending: Optional[Future] = None
        self.net = None
        if Path(model_path).is_file():
            try:
                self.net = cv2.dnn.readNetFromONNX(str(model_path))
            except Exception as e:
                logger.warning(f"ActionRecognizer disabled: {e}")

    @property
    def enabled(self) -> bool:
        return self.net is not None

    def update(self, now: float, frame_shape, poses: Dict[int, dict]) -> Dict[int, Tuple[str, str, float]]:
        """Feed one pose pass (track id → pose from assign_poses); returns the tracks whose latest
        classification is an alert action, as track id → (reason, NTU label, probability)."""
        if self.net is None:
            return {}
        arrays = {tid: a for tid, p in poses.items() if (a := _to_array(p["kpts"])) is not None}
        self._history.append((now, arrays))
        while self._history and now - self._history[0][0] > self.window:
            self._history.popleft()
        live = set(poses)
        with self._lock:
            for d in (self._last_run, self._results):
                for tid in [t for t in d if t not in live]:
                    del d[tid]
            results = dict(self._results)

        if self._pending is None or self._pending.done():
            due = [t for t in arrays if now - self._last_run.get(t, -1e9) >= self.every]
            for tid in sorted(due, key=lambda t: self._last_run.get(t, -1e9)):   # longest-waiting first
                self._last_run[tid] = now
                clip = self._clip(tid, frame_shape)
                if clip is not None:
                    self._pending = self._worker.submit(self._classify, tid, clip)
                    break
        return results

    def _classify(self, tid: int, clip: np.ndarray) -> None:
        try:
            self.net.setInput(clip)
            logits = self.net.forward()[0]
        except Exception as e:
            logger.warning(f"Action recognition error: {e}")
            return
        prob = np.exp(logits - logits.max())
        prob /= prob.sum()
        best = int(prob.argmax())
        with self._lock:
            if best in ALERT_ACTIONS and prob[best] >= self.min_confidence:
                self._results[tid] = (ALERT_ACTIONS[best], NTU60_LABELS[best], float(prob[best]))
            else:
                self._results.pop(tid, None)

    def _clip(self, tid: int, frame_shape) -> Optional[np.ndarray]:
        """(1, 2, 100, 17, 3) model input, preprocessed like mmaction2's PreNormalize2D +
        UniformSampleFrames + FormatGCNInput."""
        frames = [(t, a) for t, a in self._history if tid in a]
        if len(frames) < 4 or frames[-1][0] - frames[0][0] < 1.0:
            return None
        # The other person: whoever is closest now (no one nearby → zeros, as in NTU single-person clips)
        me = frames[-1][1][tid]
        my_h = max(1.0, float(np.ptp(me[:, 1])))
        others = [(float(np.linalg.norm(a[:, :2].mean(0) - me[:, :2].mean(0))), o)
                  for o, a in frames[-1][1].items() if o != tid]
        dist, other = min(others, default=(np.inf, None), key=lambda x: x[0])
        if dist > 2.5 * my_h:
            other = None

        # Resample to NTU's 30 fps by time (pose runs slower), then sample like mmaction2's test mode.
        times = np.array([t for t, _ in frames])
        n = int(np.clip(round((times[-1] - times[0]) * SOURCE_FPS), 1, CLIP_LEN * 4))
        picks = np.abs(times[None, :] - np.linspace(times[0], times[-1], n)[:, None]).argmin(1)
        inds = np.arange(CLIP_LEN) % n if n < CLIP_LEN else (np.arange(CLIP_LEN) * n) // CLIP_LEN
        picks = picks[inds]

        h, w = frame_shape[:2]
        scale = np.array([w / 2, h / 2], np.float32)
        clip = np.zeros((1, NUM_PERSON, CLIP_LEN, NUM_JOINTS, 3), np.float32)
        for i, k in enumerate(picks):
            people = frames[k][1]
            for m, who in enumerate((tid, other)):
                if who is not None and who in people:         # absent person stays all zeros
                    clip[0, m, i, :, :2] = (people[who][:, :2] - scale) / scale
                    clip[0, m, i, :, 2] = people[who][:, 2]
        return clip
