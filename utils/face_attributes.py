"""Soft attributes for a captured subject: estimated gender/age from the face, clothing colours.

Everything here is an estimate to help an operator describe a subject, never an identification.
Gender/age need the optional model in `models/genderage.onnx` (fetched by `ensure_local_env.py`);
without it those fields are simply absent.
"""

import os
import threading
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from utils.face_detect import YUNET_MIN_CONF, YUNET_MODEL

GENDERAGE_MODEL = Path(os.getenv("FACE_ATTR_MODEL") or Path(__file__).resolve().parents[1] / "models"
                       / "genderage.onnx")
# InsightFace buffalo_l attribute head (1.3 MB, non-commercial research licence).
GENDERAGE_URL = ("https://huggingface.co/public-data/insightface/resolve/main/models/buffalo_l/"
                 "genderage.onnx")
GENDER_MIN_CONF = float(os.getenv("FACE_ATTR_MIN_CONF", "0.8"))

_lock = threading.Lock()      # OpenCV DNN objects are not thread-safe
_net = None                   # False = unavailable
_detector = None


def _load():
    global _net, _detector
    if _net is None:
        try:
            _net = cv2.dnn.readNetFromONNX(str(GENDERAGE_MODEL)) if GENDERAGE_MODEL.is_file() else False
        except Exception:  # noqa: BLE001
            _net = False
    if _detector is None:
        try:
            _detector = cv2.FaceDetectorYN.create(str(YUNET_MODEL), "", (320, 320), YUNET_MIN_CONF, 0.3, 50) \
                if YUNET_MODEL.is_file() else False
        except Exception:  # noqa: BLE001
            _detector = False
    return _net, _detector


def face_attributes(bgr) -> dict:
    """Gender/age estimate for the largest face in `bgr`; {} when no face or no model."""
    with _lock:
        net, detector = _load()
        if not net or not detector:
            return {}
        h, w = bgr.shape[:2]
        detector.setInputSize((w, h))
        _, faces = detector.detect(bgr)
        if faces is None or not len(faces):
            return {"face_visible": False}
        x, y, bw, bh = max(faces, key=lambda f: f[2] * f[3])[:4]
        # The model expects a 96 px square centred on the face, 1.5x the face box.
        scale = 96.0 / (max(bw, bh) * 1.5)
        cx, cy = x + bw / 2, y + bh / 2
        m = np.float32([[scale, 0, 48 - cx * scale], [0, scale, 48 - cy * scale]])
        crop = cv2.warpAffine(bgr, m, (96, 96))
        net.setInput(cv2.dnn.blobFromImage(crop, 1.0, (96, 96), (0, 0, 0), swapRB=True))
        out = net.forward().flatten()
    female, male, age = float(out[0]), float(out[1]), float(out[2])
    conf = 1.0 / (1.0 + np.exp(-abs(male - female)))
    return {
        "face_visible": True,
        "gender": ("male" if male > female else "female") if conf >= GENDER_MIN_CONF else "undetermined",
        "gender_confidence": round(float(conf), 2),
        "age_estimate": int(min(90, max(1, round(age * 100)))),
    }


def _colour_name(patch) -> Optional[dict]:
    if patch.size == 0:
        return None
    b, g, r = (int(v) for v in np.median(patch.reshape(-1, 3), axis=0))
    h, s, v = (int(c) for c in cv2.cvtColor(np.uint8([[[b, g, r]]]), cv2.COLOR_BGR2HSV)[0, 0])
    if v < 55:
        name = "black"
    elif s < 40:
        name = "white" if v > 190 else "grey"
    elif h < 8 or h >= 170:
        name = "red"
    elif h < 20:
        name = "brown" if v < 150 else "orange"
    elif h < 33:
        name = "yellow"
    elif h < 85:
        name = "green"
    elif h < 100:
        name = "teal"
    elif h < 130:
        name = "blue"
    elif h < 150:
        name = "purple"
    else:
        name = "pink"
    return {"name": name, "hex": f"#{r:02x}{g:02x}{b:02x}"}


def clothing_colours(bgr) -> dict:
    """Dominant upper/lower clothing colour of a standing-person crop; {} for other shapes."""
    h, w = bgr.shape[:2]
    if h < 1.4 * w or h < 80:
        return {}
    cols = slice(int(w * 0.3), int(w * 0.7))
    out = {}
    upper = _colour_name(bgr[int(h * 0.22):int(h * 0.45), cols])
    lower = _colour_name(bgr[int(h * 0.55):int(h * 0.85), cols])
    if upper:
        out["upper_colour"] = upper
    if lower:
        out["lower_colour"] = lower
    return out


def describe(bgr) -> dict:
    """All attributes we can read from one capture of a person. Never raises: a capture must not
    be lost because its description failed."""
    try:
        return {**clothing_colours(bgr), **face_attributes(bgr)}
    except Exception:  # noqa: BLE001
        return {}
