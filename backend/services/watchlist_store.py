"""DB-backed loaders injected into the CV pipeline (keeps `core` free of backend imports)."""

import logging
from typing import List, Set, Tuple

import numpy as np

from backend.db.database import SessionLocal
from backend.models.face_encoding import FaceEncoding
from backend.models.known_person import KnownPerson
from backend.models.vehicle import LicensePlate

logger = logging.getLogger("HumanAnalysis")

ALERT_STATUSES = ("wanted", "convicted", "suspect")


def load_face_encodings() -> Tuple[List[np.ndarray], List[str]]:
    db = SessionLocal()
    try:
        encodings, names = [], []
        for rec in db.query(FaceEncoding).all():
            enc = FaceEncoding.deserialize_encoding(rec.encoding)
            if enc.size > 0:
                encodings.append(enc)
                names.append(rec.person.person_id)
        return encodings, names
    finally:
        db.close()


def load_watchlisted_plates() -> Set[str]:
    db = SessionLocal()
    try:
        return {p.plate_number for p in db.query(LicensePlate).filter(LicensePlate.watchlisted == True).all()}  # noqa: E712
    finally:
        db.close()


def load_criminal_ids() -> Set[str]:
    db = SessionLocal()
    try:
        # Everyone else stays enrolled (still recognised, so lookalikes are suppressed) but raises no alert.
        return {p.person_id for p in db.query(KnownPerson)
                .filter(KnownPerson.category == "criminal",
                        KnownPerson.criminal_status.in_(ALERT_STATUSES)).all()}
    finally:
        db.close()
