"""Face enrollment + verification against the stored watchlist.

"Training" here is enrollment: each uploaded photo yields a 128-d dlib embedding
stored in `face_encodings`; matching is nearest-neighbour on those embeddings.
The running pipeline reloads the same table (see `watchlist_store`), so new
enrollments reach live cameras within the recognizer's cache TTL.
"""

import os
import threading
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from utils.face_detect import locate_faces
from backend.models.face_encoding import FaceEncoding
from backend.models.known_person import KnownPerson
from backend.models.person_image import PersonImage

_DLIB_LOCK = threading.Lock()   # dlib models are not thread-safe
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_DIM = 1600
DEFAULT_TOLERANCE = 0.40
MIN_FACE_PX = 40            # same gates as live recognition (FaceRecognizerDB)
MIN_SHARPNESS = 25.0


class FaceError(Exception):
    """User-correctable problem with an uploaded image (maps to HTTP 4xx)."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


@dataclass
class Candidate:
    person_id: str          # public id (KnownPerson.person_id)
    name: str
    category: str
    criminal_status: str
    threat_level: int
    distance: float
    confidence: float
    is_match: bool


def get_tolerance() -> float:
    try:
        from paths import CONFIG_DIR
        from utils.config.config_loader import load_yaml
        cfg = load_yaml(os.path.join(str(CONFIG_DIR), "config.yaml"))
        return float(cfg.get("face_tolerance", DEFAULT_TOLERANCE))
    except Exception:
        return DEFAULT_TOLERANCE


def confidence(distance: float, tolerance: float) -> float:
    """Heuristic 0-1 score: 0.5 at the match threshold, 1.0 at distance 0."""
    return round(float(max(0.0, min(1.0, 1.0 - distance / (2 * tolerance)))), 3)


def _engine():
    # Lazy: a broken dlib model install can kill the process at import time.
    try:
        import face_recognition
        face_recognition.face_encodings  # noqa: B018 - stubbed module lacks it
    except BaseException as e:  # noqa: BLE001
        raise FaceError(f"Face recognition unavailable: {e}", status=503)
    return face_recognition


def decode_image(data: bytes) -> np.ndarray:
    """Bytes -> RGB uint8 array (downscaled). Raises FaceError on bad input."""
    import cv2
    if not data:
        raise FaceError("Empty file", 400)
    if len(data) > MAX_IMAGE_BYTES:
        raise FaceError(f"Image exceeds {MAX_IMAGE_BYTES // (1024 * 1024)} MB", 413)
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise FaceError("Not a readable JPG/PNG image (convert HEIC first)", 415)
    h, w = img.shape[:2]
    scale = MAX_IMAGE_DIM / max(h, w)
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def to_jpeg(rgb: np.ndarray) -> bytes:
    import cv2
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buf.tobytes() if ok else b""


def encode_faces(rgb: np.ndarray, num_jitters: int = 1):
    """Return (boxes, encodings) for every face in the image."""
    fr = _engine()
    with _DLIB_LOCK:
        boxes = locate_faces(rgb, fr, upsample=1)
        if not boxes:
            return [], []
        return boxes, fr.face_encodings(rgb, boxes, num_jitters=num_jitters)


def _check_quality(rgb: np.ndarray, box) -> None:
    """Reject photos the live recognizer would itself discard (tiny or blurry faces)."""
    import cv2
    top, right, bottom, left = box
    if min(bottom - top, right - left) < MIN_FACE_PX:
        raise FaceError(f"Face too small (< {MIN_FACE_PX}px); use a closer photo")
    crop = cv2.cvtColor(rgb[top:bottom, left:right], cv2.COLOR_RGB2GRAY)
    if cv2.Laplacian(crop, cv2.CV_64F).var() < MIN_SHARPNESS:
        raise FaceError("Face is too blurry; use a sharper photo")


def encode_single_face(rgb: np.ndarray) -> np.ndarray:
    """Enrollment needs exactly one unambiguous face."""
    boxes, encs = encode_faces(rgb, num_jitters=3)
    if not boxes:
        raise FaceError("No face detected in image")
    if len(boxes) > 1:
        raise FaceError(f"{len(boxes)} faces detected; upload a photo with one face")
    _check_quality(rgb, boxes[0])
    return encs[0]


def rank_candidates(probe: np.ndarray, db, tolerance: float, top_k: int = 5,
                    only_person: Optional[int] = None) -> List[Candidate]:
    """Best distance per person, ascending. Optionally restrict to one person (1:1)."""
    q = db.query(FaceEncoding)
    if only_person is not None:
        q = q.filter(FaceEncoding.person_id == only_person)
    rows = q.all()
    if not rows:
        return []
    encs = [FaceEncoding.deserialize_encoding(r.encoding) for r in rows]
    keep = [(r, e) for r, e in zip(rows, encs) if e.size == 128]
    if not keep:
        return []
    dists = np.linalg.norm(np.stack([e for _, e in keep]) - probe, axis=1)
    best = {}
    for (r, _), d in zip(keep, dists):
        if r.person_id not in best or d < best[r.person_id]:
            best[r.person_id] = float(d)
    persons = {p.id: p for p in db.query(KnownPerson).filter(KnownPerson.id.in_(best)).all()}
    out = []
    for pid, d in sorted(best.items(), key=lambda kv: kv[1])[:top_k]:
        p = persons.get(pid)
        if p is None:
            continue
        out.append(Candidate(
            person_id=p.person_id, name=p.name, category=p.category,
            criminal_status=p.criminal_status or "unknown", threat_level=p.threat_level or 0,
            distance=round(d, 4), confidence=confidence(d, tolerance), is_match=d <= tolerance,
        ))
    return out


def enroll_image(db, person: KnownPerson, data: bytes, filename: Optional[str], tolerance: float) -> dict:
    """Validate, encode and store one photo for `person`. Caller commits."""
    rgb = decode_image(data)
    enc = encode_single_face(rgb)
    # Flag (don't block) a face that already matches someone else.
    dup = [c for c in rank_candidates(enc, db, tolerance, top_k=3)
           if c.is_match and c.person_id != person.person_id]
    img = PersonImage(person_id=person.id, image_data=to_jpeg(rgb), image_type="face", filename=filename)
    db.add(img)
    db.flush()
    db.add(FaceEncoding(person_id=person.id, image_id=img.id,
                        encoding=FaceEncoding.serialize_encoding(enc)))
    return {"image_id": img.id, "filename": filename,
            "possible_duplicate_of": [{"person_id": c.person_id, "name": c.name,
                                       "distance": c.distance} for c in dup]}


def verify_bytes(db, data: bytes, target: Optional[KnownPerson], tolerance: float) -> dict:
    """Match every face in an image against stored records (1:N, or 1:1 when `target`).

    status: match | no_match | no_face. Raises FaceError for unreadable images.
    """
    rgb = decode_image(data)
    boxes, encs = encode_faces(rgb)
    faces = []
    for (top, right, bottom, left), enc in zip(boxes, encs):
        cands = rank_candidates(enc, db, tolerance, top_k=5, only_person=target.id if target else None)
        faces.append({"box": {"top": top, "right": right, "bottom": bottom, "left": left},
                      "candidates": [c.__dict__ for c in cands],
                      "best": cands[0].__dict__ if cands and cands[0].is_match else None})
    if not faces:
        status = "no_face"
    else:
        status = "match" if any(f["best"] for f in faces) else "no_match"
    best = min((f["best"] for f in faces if f["best"]), key=lambda c: c["distance"], default=None)
    return {"status": status, "mode": "1:1" if target else "1:N", "threshold": tolerance,
            "image": {"width": int(rgb.shape[1]), "height": int(rgb.shape[0])},
            "face_count": len(faces), "best_match": best, "faces": faces}
