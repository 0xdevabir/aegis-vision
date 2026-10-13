"""Runtime configuration entries (thresholds, alert rules)."""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.auth import operator_or_admin, admin_only
from backend.auth.guards import verify_internal_key
from backend.models.audit_log import AuditLog
from backend.db.database import get_db
from backend.models.config_entry import ConfigEntry
from backend.models.user import User

router = APIRouter(prefix="/config", tags=["config"])

# The only thresholds the pipeline actually honours at runtime: key → (min, max, default).
THRESHOLD_SPECS = {
    "threshold.confidence_threshold": (0.30, 0.90, 0.50),    # person detection
    "threshold.weapon_conf_threshold": (0.20, 0.90, 0.40),   # weapon detection
    "threshold.face_tolerance": (0.35, 0.60, 0.45),          # lower = stricter match
    "threshold.loiter_seconds": (5, 120, 15),
    "threshold.crowd_threshold": (2, 30, 5),
}


class ConfigEntryIn(BaseModel):
    value: str
    description: Optional[str] = None


class ConfigEntryOut(BaseModel):
    key: str
    value: Optional[str]
    description: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/", response_model=list[ConfigEntryOut])
def list_config(db: Session = Depends(get_db), user: User = Depends(operator_or_admin)):
    return db.query(ConfigEntry).order_by(ConfigEntry.key).all()


@router.get("/runtime")
def runtime_config(
    camera_id: Optional[str] = None,
    x_internal_key: Optional[str] = Header(default=None, alias="X-Internal-Key"),
    db: Session = Depends(get_db),
):
    """Pipeline polls this to pick up threshold and zone changes without a restart.

    Flat threshold numbers stay at the top level; per-camera geometry is under
    "geometry" and is null when the dashboard has never configured that camera.
    """
    verify_internal_key(x_internal_key)
    out = {k: float(v) for k, v in _effective_thresholds(db).items()}
    geometry = None
    if camera_id:
        import json
        from backend.models.camera import Camera
        cam = db.query(Camera).filter(Camera.camera_id == camera_id).first()
        if cam and cam.geometry:
            try:
                geometry = json.loads(cam.geometry)
            except ValueError:
                geometry = None
    out["geometry"] = geometry
    return out


@router.get("/{key}")
def get_config(key: str, db: Session = Depends(get_db), user: User = Depends(operator_or_admin)):
    entry = db.query(ConfigEntry).filter(ConfigEntry.key == key).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Config key not found")
    return {"key": entry.key, "value": entry.value, "description": entry.description}


@router.put("/{key}")
def upsert_config(
    key: str,
    body: ConfigEntryIn,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
):
    spec = THRESHOLD_SPECS.get(key)
    if key.startswith("threshold.") and spec is None:
        raise HTTPException(status_code=400, detail=f"Unknown threshold. Allowed: {', '.join(THRESHOLD_SPECS)}")
    if spec:
        try:
            val = float(body.value)
        except ValueError:
            raise HTTPException(status_code=400, detail="Threshold must be a number")
        if not spec[0] <= val <= spec[1]:
            raise HTTPException(status_code=400, detail=f"{key} must be between {spec[0]} and {spec[1]}")
    entry = db.query(ConfigEntry).filter(ConfigEntry.key == key).first()
    old = entry.value if entry else None
    db.add(AuditLog(
        user_id=admin.id, username=admin.username, action="CONFIG_CHANGE",
        resource="config", resource_id=key, details=f"{old!r} -> {body.value!r}",
    ))
    if entry:
        entry.value = body.value
        entry.description = body.description or entry.description
        entry.updated_by = admin.id
    else:
        entry = ConfigEntry(key=key, value=body.value, description=body.description, updated_by=admin.id)
        db.add(entry)
    db.commit()
    return {"status": "saved", "key": key}


@router.get("/thresholds/all")
def get_thresholds(db: Session = Depends(get_db), user: User = Depends(operator_or_admin)):
    """Effective thresholds (defaults merged with stored values) plus allowed ranges."""
    return _effective_thresholds(db)


def _effective_thresholds(db: Session) -> dict:
    values = {k.replace("threshold.", ""): str(v[2]) for k, v in THRESHOLD_SPECS.items()}
    for row in db.query(ConfigEntry).filter(ConfigEntry.key.like("threshold.%")).all():
        if row.key in THRESHOLD_SPECS:
            values[row.key.replace("threshold.", "")] = row.value
    return values


@router.get("/thresholds/specs")
def threshold_specs(user: User = Depends(operator_or_admin)):
    return {k.replace("threshold.", ""): {"min": v[0], "max": v[1], "default": v[2]}
            for k, v in THRESHOLD_SPECS.items()}
