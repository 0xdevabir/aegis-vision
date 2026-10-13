import cv2
import numpy as np
from backend.db.database import SessionLocal
from backend.models.evidence import Evidence
from backend.utils.encryption import EncryptionManager
from backend.services.custody import append_custody, sha256_bytes
from utils import logger


def save_evidence_db(
    camera_location: str,
    track_id: int,
    person_name: str,
    is_criminal: bool,
    weapon_present: bool,
    is_suspicious: bool,
    reasons: list,
    frame: np.ndarray,
    roi: np.ndarray,
    encrypt: bool = False,
):
    db = SessionLocal()
    try:
        _, frame_buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        frame_bytes = frame_buffer.tobytes()
        _, roi_buffer = cv2.imencode(".jpg", roi, [cv2.IMWRITE_JPEG_QUALITY, 85])
        roi_bytes = roi_buffer.tobytes()
        content_hash = sha256_bytes(frame_bytes)
        if encrypt:
            enc_manager = EncryptionManager()
            frame_bytes = enc_manager.encrypt(frame_bytes)
            roi_bytes = enc_manager.encrypt(roi_bytes)
        category = "criminal" if is_criminal else "weapon" if weapon_present else "suspicious"
        reason_text = ", ".join(reasons) if reasons else None
        evidence = Evidence(
            camera_location=camera_location,
            track_id=track_id,
            person_name=person_name,
            is_criminal=is_criminal,
            weapon_present=weapon_present,
            is_suspicious=is_suspicious,
            reasons=reason_text,
            category=category,
            frame_data=frame_bytes,
            roi_data=roi_bytes,
            encrypted=encrypt,
            content_sha256=content_hash,
        )
        db.add(evidence)
        db.flush()
        append_custody(
            db,
            evidence_id=evidence.id,
            action="CAPTURED",
            actor="SYSTEM",
            sha256_hash=content_hash,
            details=f"{category} / track {track_id} / {camera_location}",
        )
        db.commit()
        logger.info(f"Evidence saved: {category} / {person_name} / track {track_id} / sha256={content_hash[:12]}…")
    except Exception as e:
        logger.error(f"Evidence save failed: {e}")
        db.rollback()
    finally:
        db.close()
