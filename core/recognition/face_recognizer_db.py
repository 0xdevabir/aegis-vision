import logging
import time
from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np

from core.detectors.device import shared_inference_lock
from core.recognition.face_worker import shared_pool
from utils.face_detect import detect_and_encode, quality_ok

# In-process fallback only (out_of_process=False, e.g. tests). dlib's detector/encoder are shared
# module-level objects, not thread-safe, and running them next to PyTorch/MPS segfaulted the process,
# so here they take turns with the MPS detectors on one lock. The live pipeline uses worker processes
# instead (core/recognition/face_worker.py): no lock, face work runs in parallel with YOLO.
_DLIB_LOCK = shared_inference_lock()

# dlib (face_recognition) loads ~130 MB of models on import. The live pipeline does all face work in
# worker processes, so it must not pay that here: on an 8 GB machine it is the difference between
# fitting in RAM and swapping. Loaded lazily, only by the in-process fallback.
face_recognition = None


def _dlib():
    global face_recognition
    if face_recognition is None:
        import face_recognition as fr
        face_recognition = fr
    return face_recognition

logger = logging.getLogger("HumanAnalysis")

Loader = Callable[[], Tuple[List[np.ndarray], List[str]]]


class FaceRecognizerDB:
    """dlib face matcher with quality gating and a best-vs-second-best margin.

    Encodings come from an injected `loader` (the composition root supplies the DB
    one) and are refreshed every `cache_ttl` seconds so watchlist edits reach a
    running pipeline without a restart.
    """

    def __init__(self, tolerance: float = 0.45, loader: Optional[Loader] = None,
                 cache_ttl: float = 60.0, min_face_px: int = 40,
                 min_sharpness: float = 25.0, min_margin: float = 0.04,
                 solo_slack: float = 0.0, cnn_cooldown: float = 3.0, out_of_process: bool = False):
        self.tolerance = tolerance
        self.loader = loader or (lambda: ([], []))
        self.cache_ttl = cache_ttl
        self.min_face_px = min_face_px
        self.min_sharpness = min_sharpness
        self.min_margin = min_margin
        self.solo_slack = solo_slack            # extra strictness when no rival identity exists to compare
        # Seconds between slow CNN fallbacks, per caller (camera). One shared timer let a camera whose
        # CNN keeps missing (faceless tracks) lock every other camera out of the CNN, and some webcams
        # only ever find faces via CNN: a second camera then never confirmed a watchlist match.
        self.cnn_cooldown = cnn_cooldown
        self._last_cnn: dict = {}
        # Run dlib in worker processes (the live pipeline does): no lock against YOLO, and a dlib
        # crash or hang costs a worker, not the pipeline.
        self.out_of_process = out_of_process
        self._cache = None
        self._loaded_at = 0.0

    def _load_encodings(self):
        if self._cache is None or time.time() - self._loaded_at > self.cache_ttl:
            self._cache = self.loader()
            self._loaded_at = time.time()
        return self._cache

    def _quality_ok(self, rgb, box) -> bool:
        return quality_ok(rgb, box, self.min_face_px, self.min_sharpness)

    def match(self, distances: np.ndarray, names: List[str]) -> Optional[Tuple[str, float, float]]:
        """Pure matching logic: (person, distance, margin) or None."""
        best = {}
        for d, n in zip(distances, names):
            if n not in best or d < best[n]:
                best[n] = float(d)
        ranked = sorted(best.items(), key=lambda kv: kv[1])
        if not ranked or ranked[0][1] > self.tolerance:
            return None
        if len(ranked) > 1:
            margin = ranked[1][1] - ranked[0][1]
            if margin < self.min_margin:
                return None
        else:
            # Single enrolled identity: no rival to rank against. `solo_slack` (default 0) can demand a
            # tighter match, but real webcam distances for the true person are ~0.40-0.45, so keep it small.
            if ranked[0][1] > self.tolerance - self.solo_slack:
                return None
            margin = self.tolerance - ranked[0][1]
        return ranked[0][0], ranked[0][1], margin

    def recognize_detail(self, face_roi, source=None) -> Optional[dict]:
        """`source` keys the slow-detector (CNN) cooldown. Pass one per person (camera + track), so a
        faceless track can neither starve the real target nor another camera of the CNN."""
        rgb = cv2.cvtColor(face_roi, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        upsample = 3 if (h < 120 or w < 120) else 2 if (h < 300 or w < 300) else 1

        now = time.time()
        use_cnn = now - self._last_cnn.get(source, 0.0) >= self.cnn_cooldown
        if self.out_of_process:
            encoding, cnn_missed = shared_pool().detect_and_encode(
                rgb, upsample, use_cnn, self.min_face_px, self.min_sharpness)
        else:
            with _DLIB_LOCK:
                encoding, cnn_missed = detect_and_encode(rgb, upsample, use_cnn, self.min_face_px,
                                                         self.min_sharpness, _dlib())
        if cnn_missed:
            self._last_cnn[source] = now        # CNN ran and missed: wait before the next one
            if len(self._last_cnn) > 512:       # per-person keys: drop the stale ones
                self._last_cnn = {k: t for k, t in self._last_cnn.items() if now - t < 60}
        if encoding is None:
            return None
        known_encodings, known_names = self._load_encodings()
        if not known_encodings:
            return None
        distances = np.linalg.norm(np.asarray(known_encodings) - encoding, axis=1)   # = face_distance
        res = self.match(distances, known_names)
        if res is None:
            return None
        return {"name": res[0], "distance": res[1], "margin": res[2]}

    def recognize_person(self, face_roi, source=None) -> Optional[str]:
        res = self.recognize_detail(face_roi, source=source)
        return res["name"] if res else None

    @staticmethod
    def confidence(distance: float, tolerance: float) -> float:
        """0-1 heuristic: 1.0 at distance 0, 0.5 at the tolerance (same as the registry's verify)."""
        return round(max(0.0, min(1.0, 1.0 - distance / (2 * tolerance))), 3)

    def invalidate_cache(self):
        self._cache = None
