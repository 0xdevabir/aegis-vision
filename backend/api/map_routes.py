"""Data for the operations map: every camera (with status) and recent alerts placed on it."""
import json
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.auth import operator_or_admin
from backend.db.database import get_db
from backend.models.alert import Alert
from backend.models.camera import Camera
from backend.models.user import User

router = APIRouter(prefix="/map", tags=["map"])

HIDDEN_TYPES = {"PIPELINE_HEARTBEAT"}


class CameraMapResponse(BaseModel):
    camera_id: str
    name: str
    location: Optional[str]
    lat: Optional[float]
    lng: Optional[float]
    active: bool
    heading: Optional[float] = None
    fov: Optional[float] = None
    range_m: Optional[float] = None

    class Config:
        from_attributes = True


class MapEvent(BaseModel):
    alert_id: int
    event_type: str
    lat: Optional[float]
    lng: Optional[float]
    camera_id: Optional[str]
    camera_name: Optional[str]
    severity: str
    timestamp: str
    description: str
    person_name: Optional[str] = None
    acknowledged: bool = False


@router.get("/cameras", response_model=List[CameraMapResponse])
def get_camera_positions(db: Session = Depends(get_db), user: User = Depends(operator_or_admin)):
    """Every camera, including switched-off ones and ones without GPS, so the map can flag them."""
    return db.query(Camera).order_by(Camera.camera_id).all()


@router.get("/events", response_model=List[MapEvent])
def get_map_events(
    hours: int = Query(24, ge=1, le=168),
    types: Optional[str] = Query(None, description="Comma-separated alert types"),
    limit: int = Query(500, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    """Recent alerts with the position they were raised at (GPS stored with the alert, else the camera's)."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    q = db.query(Alert).filter(Alert.timestamp >= cutoff, Alert.alert_type.notin_(HIDDEN_TYPES),
                               Alert.review_status != "rejected")
    if types:
        q = q.filter(Alert.alert_type.in_([t.strip() for t in types.split(",") if t.strip()]))
    cameras = {c.camera_id: c for c in db.query(Camera).all()}
    out = []
    for a in q.order_by(Alert.timestamp.desc()).limit(limit).all():
        cam = cameras.get(a.camera_id)
        lat = lng = None
        if a.details:
            try:
                geo = json.loads(a.details)
                lat, lng = geo.get("lat"), geo.get("lng")
            except Exception:  # noqa: BLE001
                pass
        if lat is None and cam is not None:
            lat, lng = cam.lat, cam.lng
        out.append(MapEvent(
            alert_id=a.id, event_type=a.alert_type, lat=lat, lng=lng,
            camera_id=a.camera_id, camera_name=cam.name if cam else a.camera_location,
            severity=a.severity, timestamp=a.timestamp.isoformat() if a.timestamp else "",
            description=(a.message or a.alert_type).split(" | ")[0].split(" — GPS")[0],
            person_name=a.person_name, acknowledged=bool(a.acknowledged),
        ))
    return out
