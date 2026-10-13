"""Cross-camera re-identification — same person / plate across cameras."""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.db.database import get_db
from backend.models.user import User
from backend.models.evidence import Evidence
from backend.models.alert import Alert
from backend.models.vehicle import VehicleDetection
from backend.auth.auth import operator_or_admin

router = APIRouter(prefix="/reid", tags=["reid"])


@router.get("/persons")
def person_tracks(
    hours: int = 24,
    name: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    """
    Group detections of the same person_name across cameras.
    Uses identity labels from the face recognizer (watchlist matches).
    """
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    q = db.query(Evidence).filter(
        Evidence.timestamp >= cutoff,
        Evidence.person_name.isnot(None),
        Evidence.person_name != "Unknown",
    )
    if name:
        q = q.filter(Evidence.person_name.ilike(f"%{name}%"))
    rows = q.order_by(desc(Evidence.timestamp)).limit(500).all()

    by_person = defaultdict(list)
    for r in rows:
        by_person[r.person_name].append({
            "evidence_id": r.id,
            "camera": r.camera_location,
            "camera_id": r.camera_id,
            "track_id": r.track_id,
            "category": r.category,
            "is_criminal": r.is_criminal,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "has_image": bool(r.frame_data),
        })

    tracks = []
    for person, sightings in by_person.items():
        cameras = sorted({s["camera"] or s["camera_id"] or "?" for s in sightings})
        tracks.append({
            "person_name": person,
            "sightings": len(sightings),
            "cameras": cameras,
            "cross_camera": len(cameras) > 1,
            "first_seen": sightings[-1]["timestamp"] if sightings else None,
            "last_seen": sightings[0]["timestamp"] if sightings else None,
            "path": sightings[:20],
        })
    tracks.sort(key=lambda t: (not t["cross_camera"], -t["sightings"]))
    return {"period_hours": hours, "persons": tracks}


@router.get("/persons/{person_name}")
def person_journey(
    person_name: str,
    hours: int = 72,
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    evidence = (
        db.query(Evidence)
        .filter(Evidence.person_name == person_name, Evidence.timestamp >= cutoff)
        .order_by(Evidence.timestamp.asc())
        .all()
    )
    alerts = (
        db.query(Alert)
        .filter(Alert.person_name == person_name, Alert.timestamp >= cutoff)
        .order_by(Alert.timestamp.asc())
        .all()
    )
    return {
        "person_name": person_name,
        "cameras": sorted({e.camera_location for e in evidence if e.camera_location}),
        "evidence": [
            {
                "id": e.id,
                "camera": e.camera_location,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "category": e.category,
            }
            for e in evidence
        ],
        "alerts": [
            {
                "id": a.id,
                "type": a.alert_type,
                "camera": a.camera_location,
                "timestamp": a.timestamp.isoformat() if a.timestamp else None,
            }
            for a in alerts
        ],
    }


@router.get("/vehicles")
def vehicle_tracks(
    hours: int = 24,
    plate: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    q = db.query(VehicleDetection).filter(VehicleDetection.timestamp >= cutoff)
    if plate:
        q = q.filter(VehicleDetection.license_plate.ilike(f"%{plate}%"))
    rows = q.order_by(desc(VehicleDetection.timestamp)).limit(500).all()

    by_plate = defaultdict(list)
    for r in rows:
        key = (r.license_plate or "UNKNOWN").upper()
        by_plate[key].append({
            "id": r.id,
            "camera": r.camera_location,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "is_suspicious": r.is_suspicious,
            "vehicle_type": r.vehicle_type,
        })

    tracks = []
    for p, sightings in by_plate.items():
        cams = sorted({str(s["camera"] or "?") for s in sightings})
        tracks.append({
            "plate_number": p,
            "sightings": len(sightings),
            "cameras": cams,
            "cross_camera": len(cams) > 1,
            "path": sightings[:20],
        })
    tracks.sort(key=lambda t: (not t["cross_camera"], -t["sightings"]))
    return {"period_hours": hours, "vehicles": tracks}

