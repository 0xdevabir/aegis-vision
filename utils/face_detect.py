"""Face localisation: fast HOG first, accurate CNN when HOG finds nothing.

dlib's HOG detector is fast but misses faces that are dim, low-contrast, slightly turned
or partly occluded; on this project's laptop webcam it found no face in any frame while
the CNN detector found it every time. The CNN costs seconds on CPU, so it only runs as
a fallback, on a downscaled copy, and callers can gate it.
"""

import os
from pathlib import Path
from typing import List, Optional, Tuple

Box = Tuple[int, int, int, int]          # (top, right, bottom, left) like face_recognition

YUNET_MODEL = Path(os.getenv("FACE_YUNET_MODEL") or Path(__file__).resolve().parents[1] / "models"
                   / "face_detection_yunet_2023mar.onnx")
YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
             "face_detection_yunet_2023mar.onnx")
YUNET_MIN_CONF = float(os.getenv("FACE_YUNET_MIN_CONF", "0.7"))
_yunet = None          # per-process detector; False = unavailable (missing model / old OpenCV)

CNN_ENABLED = os.getenv("FACE_CNN_FALLBACK", "true").lower() == "true"
CNN_MAX_DIM = int(os.getenv("FACE_CNN_MAX_DIM", "640"))


def yunet_boxes(rgb) -> Optional[List[Box]]:
    """Faces via OpenCV's YuNet: 5-15 ms on a person crop, against ~100 ms for dlib's HOG and
    200-500 ms for its CNN, with the same recall on this project's webcams. Its boxes encode as well
    as dlib's own (match distance 0.413 vs 0.415 and 0.320 vs 0.328 on the same faces).
    Returns None when YuNet is unavailable so the caller falls back to dlib."""
    global _yunet
    if _yunet is None:
        try:
            import cv2
            _yunet = cv2.FaceDetectorYN.create(str(YUNET_MODEL), "", (320, 320), YUNET_MIN_CONF, 0.3, 50) \
                if YUNET_MODEL.is_file() else False
        except Exception:  # noqa: BLE001
            _yunet = False
    if not _yunet:
        return None
    import cv2
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]
    _yunet.setInputSize((w, h))
    _, faces = _yunet.detect(bgr)
    boxes = []
    for f in (faces if faces is not None else []):
        x, y, bw, bh = f[:4]
        boxes.append((max(0, int(y)), min(w, int(x + bw)), min(h, int(y + bh)), max(0, int(x))))
    return boxes


def cnn_faces(rgb, face_recognition, cnn_max_dim: int = CNN_MAX_DIM) -> List[Box]:
    """dlib CNN detector on a downscaled copy; boxes come back in `rgb`'s coordinates."""
    import cv2
    h, w = rgb.shape[:2]
    scale = min(1.0, cnn_max_dim / max(h, w))
    small = cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else rgb
    found = face_recognition.face_locations(small, model="cnn", number_of_times_to_upsample=0)
    if scale >= 1:
        return list(found)
    inv = 1.0 / scale
    return [(max(0, int(t * inv)), min(w, int(r * inv)), min(h, int(b * inv)), max(0, int(l * inv)))
            for (t, r, b, l) in found]


def locate_faces(rgb, face_recognition, *, upsample: int = 1, cnn_fallback: bool = True,
                 cnn_max_dim: int = CNN_MAX_DIM) -> List[Box]:
    """Return face boxes in `rgb`'s own coordinates. The caller holds any dlib lock."""
    boxes = face_recognition.face_locations(rgb, model="hog", number_of_times_to_upsample=upsample)
    if boxes or not (cnn_fallback and CNN_ENABLED):
        return list(boxes)
    return cnn_faces(rgb, face_recognition, cnn_max_dim)


def quality_ok(rgb, box, min_face_px: int, min_sharpness: float) -> bool:
    """Big enough and sharp enough to encode reliably."""
    import cv2
    top, right, bottom, left = box
    if min(bottom - top, right - left) < min_face_px:
        return False
    crop = cv2.cvtColor(rgb[top:bottom, left:right], cv2.COLOR_RGB2GRAY)
    return cv2.Laplacian(crop, cv2.CV_64F).var() >= min_sharpness


def detect_and_encode(rgb, upsample: int, use_cnn: bool, min_face_px: int, min_sharpness: float,
                      face_recognition=None):
    """Locate the largest good face in `rgb` and encode it: (encoding | None, cnn_missed).

    Top-level and import-light so it can run in a worker process: dlib holds the GIL for
    the whole call, so in the pipeline process it froze video and YOLO for every camera.
    `cnn_missed` is True when the CNN fallback ran and still found nothing.
    """
    if face_recognition is None:
        import face_recognition
    boxes = yunet_boxes(rgb)
    if boxes is None:                                   # no YuNet: dlib HOG, then CNN
        boxes = locate_faces(rgb, face_recognition, upsample=upsample, cnn_fallback=use_cnn)
    elif not boxes and use_cnn and CNN_ENABLED:         # YuNet found none: CNN for hard (turned/dim) faces
        boxes = cnn_faces(rgb, face_recognition)
    cnn_missed = use_cnn and not boxes
    boxes = [b for b in boxes if quality_ok(rgb, b, min_face_px, min_sharpness)]
    if not boxes:
        return None, cnn_missed
    box = max(boxes, key=lambda b: (b[2] - b[0]) * (b[1] - b[3]))       # largest face only
    encodings = face_recognition.face_encodings(rgb, [box])
    return (encodings[0] if encodings else None), cnn_missed
