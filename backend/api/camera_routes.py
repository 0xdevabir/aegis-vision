from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List
import urllib.parse
import requests
import logging
from backend.db.database import get_db
from backend.models.camera import Camera
from backend.models.user import User
from backend.auth.auth import operator_or_admin, admin_only, supervisor_or_admin
from backend.models.audit_log import AuditLog
from backend.services.audit import log_audit
from core.analysis.zones import validate_geometry
import json
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cameras", tags=["cameras"])

@router.get("/resolve-ip")
def resolve_ip(url: str = Query(..., description="IP or URL of the camera"), user: User = Depends(operator_or_admin)):
    try:
        parsed = urllib.parse.urlparse(url)
        hostname = parsed.hostname or url
        # Remove any port if hostname somehow includes it (urlparse usually handles it)
        if ":" in hostname:
            hostname = hostname.split(":")[0]
            
        resp = requests.get(f"http://ip-api.com/json/{hostname}", timeout=5)
        data = resp.json()
        
        if data.get("status") == "success":
            location = f"{data.get('city', '')}, {data.get('country', '')}".strip(", ")
            return {
                "ip": data.get("query"),
                "location": location,
                "lat": data.get("lat"),
                "lng": data.get("lon")
            }
        else:
            return {
                "ip": hostname,
                "location": "",
                "lat": None,
                "lng": None,
                "error": data.get("message", "Unknown error")
            }
    except Exception as e:
        logger.error(f"Failed to resolve IP {url}: {e}")
        return {
            "ip": url,
            "location": "",
            "lat": None,
            "lng": None,
            "error": str(e)
        }


class CameraCreate(BaseModel):
    camera_id: str
    name: str
    location: Optional[str] = None
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lng: Optional[float] = Field(None, ge=-180, le=180)
    rtsp_url: Optional[str] = None
    active: Optional[bool] = True
    heading: Optional[float] = None
    fov: Optional[float] = None
    range_m: Optional[float] = None


class CameraResponse(BaseModel):
    id: int
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


@router.get("/", response_model=List[CameraResponse])
def list_cameras(db: Session = Depends(get_db), user: User = Depends(operator_or_admin)):
    # Auto-sync cameras from cameras.yaml into DB
    yaml_path = Path(__file__).resolve().parents[2] / "config" / "cameras.yaml"   # not cwd-dependent
    if yaml_path.exists():
        try:
            with open(yaml_path, "r") as f:
                ydata = yaml.safe_load(f) or {}
            existing = {c.camera_id: c for c in db.query(Camera).all()}
            existing_ids = set(existing)
            for cam in ydata.get("cameras", []):
                cam_id = cam.get("id")
                if cam_id in existing:
                    # cameras.yaml is what the pipeline actually runs: mirror its enabled flag.
                    existing[cam_id].active = bool(cam.get("enabled", True))
                    continue
                if cam_id and cam_id not in existing_ids:
                    db.add(Camera(
                        camera_id=cam_id,
                        name=cam.get("name", cam_id),
                        location=cam.get("location", ""),
                        lat=cam.get("lat"),
                        lng=cam.get("lng"),
                        rtsp_url=cam.get("source", ""),
                        active=cam.get("enabled", True),
                    ))
                    existing_ids.add(cam_id)
            db.commit()
        except Exception as e:
            logger.error(f"Failed to sync cameras from YAML: {e}")
            db.rollback()
    return db.query(Camera).all()


import yaml
from pathlib import Path

def sync_camera_to_yaml(cam: Camera):
    yaml_path = Path("config/cameras.yaml")
    if not yaml_path.exists():
        return
    try:
        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f) or {"cameras": []}
            
        cameras = data.get("cameras", [])
        found = False
        for c in cameras:
            if c.get("id") == cam.camera_id:
                c["name"] = cam.name
                if cam.rtsp_url:                      # never blank a working source on a plain on/off toggle
                    c["source"] = cam.rtsp_url
                if cam.location is not None:
                    c["location"] = cam.location
                if cam.lat is not None:
                    c["lat"] = cam.lat
                if cam.lng is not None:
                    c["lng"] = cam.lng
                c["enabled"] = cam.active
                found = True
                break
                
        if not found and cam.active:
            cameras.append({
                "id": cam.camera_id,
                "name": cam.name,
                "source": cam.rtsp_url,
                "location": cam.location,
                "lat": cam.lat,
                "lng": cam.lng,
                "enabled": True,
                "fps_limit": 15,
                "priority": "high"
            })
            
        data["cameras"] = cameras
        with open(yaml_path, "w") as f:
            yaml.safe_dump(data, f, sort_keys=False)
    except Exception as e:
        logger.error(f"Failed to sync camera to yaml: {e}")

@router.post("/", response_model=CameraResponse)
def create_camera(cam: CameraCreate, request: Request, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    existing = db.query(Camera).filter(Camera.camera_id == cam.camera_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Camera ID already exists")
    camera = Camera(**cam.model_dump())
    db.add(camera)
    log_audit(db, admin, "CAMERA_CREATE", "camera", cam.camera_id, f"name={cam.name}", request)
    db.commit()
    db.refresh(camera)
    sync_camera_to_yaml(camera)
    return camera


@router.put("/{camera_id}", response_model=CameraResponse)
def update_camera(camera_id: str, cam: CameraCreate, request: Request, db: Session = Depends(get_db),
                  admin: User = Depends(admin_only)):
    camera = db.query(Camera).filter(Camera.camera_id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    changes = cam.model_dump(exclude_unset=True)
    for key, val in changes.items():
        setattr(camera, key, val)
    shown = {k: v for k, v in changes.items() if k != "rtsp_url"}    # URLs may embed credentials
    log_audit(db, admin, "CAMERA_UPDATE", "camera", camera_id, str(shown), request)
    db.commit()
    db.refresh(camera)
    sync_camera_to_yaml(camera)
    return camera


@router.delete("/{camera_id}")
def delete_camera(camera_id: str, request: Request, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    camera = db.query(Camera).filter(Camera.camera_id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    camera.active = False
    sync_camera_to_yaml(camera)
    log_audit(db, admin, "CAMERA_DELETE", "camera", camera_id, f"name={camera.name}", request)
    db.delete(camera)
    db.commit()
    return {"status": "deleted"}


class GeometryBody(BaseModel):
    zones: list = []
    lines: list = []


def _geometry_of(cam: Camera) -> dict:
    if not cam.geometry:
        return {"zones": [], "lines": []}
    try:
        g = json.loads(cam.geometry)
        return {"zones": g.get("zones", []), "lines": g.get("lines", [])}
    except ValueError:
        return {"zones": [], "lines": []}


@router.get("/{camera_id}/geometry")
def get_geometry(camera_id: str, db: Session = Depends(get_db), user: User = Depends(operator_or_admin)):
    cam = db.query(Camera).filter(Camera.camera_id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    return {**_geometry_of(cam), "configured": cam.geometry is not None,
            "updated_at": cam.geometry_updated_at.isoformat() if cam.geometry_updated_at else None}


@router.put("/{camera_id}/geometry")
def put_geometry(camera_id: str, body: GeometryBody, db: Session = Depends(get_db),
                 user: User = Depends(supervisor_or_admin)):
    """Replace a camera's zones and lines. Cameras pick it up within ~30 s."""
    cam = db.query(Camera).filter(Camera.camera_id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    try:
        clean = validate_geometry(body.zones, body.lines)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    before = _geometry_of(cam)
    cam.geometry = json.dumps(clean)
    cam.geometry_updated_at = datetime.utcnow()
    db.add(AuditLog(
        user_id=user.id, username=user.username, action="GEOMETRY_CHANGE",
        resource="camera", resource_id=camera_id,
        details=f"zones {len(before['zones'])}->{len(clean['zones'])}, "
                f"lines {len(before['lines'])}->{len(clean['lines'])}",
    ))
    db.commit()
    return {**clean, "configured": True, "updated_at": cam.geometry_updated_at.isoformat()}


class OfficerAssign(BaseModel):
    user_ids: List[int]          # first = primary officer, rest = backups


@router.get("/{camera_id}/officers")
def get_camera_officers(camera_id: str, db: Session = Depends(get_db), user: User = Depends(operator_or_admin)):
    from backend.services.officer_dispatch import officers_for_camera, officer_summary
    return {"camera_id": camera_id, "officers": officer_summary(officers_for_camera(db, camera_id))}


@router.put("/{camera_id}/officers")
def set_camera_officers(camera_id: str, body: OfficerAssign, request: Request, db: Session = Depends(get_db),
                        admin: User = Depends(admin_only)):
    from backend.models.camera_officer import CameraOfficer
    if not db.query(Camera).filter(Camera.camera_id == camera_id).first():
        raise HTTPException(status_code=404, detail="Camera not found")
    ids = list(dict.fromkeys(body.user_ids))
    good = {u.id for u in db.query(User).filter(User.id.in_(ids), User.role == "police", User.is_active == True).all()}  # noqa: E712
    bad = [i for i in ids if i not in good]
    if bad:
        raise HTTPException(status_code=422, detail=f"Not active police users: {bad}")
    db.query(CameraOfficer).filter(CameraOfficer.camera_id == camera_id).delete()
    for prio, uid in enumerate(ids):
        db.add(CameraOfficer(camera_id=camera_id, user_id=uid, priority=prio))
    log_audit(db, admin, "OFFICER_ASSIGN", "camera", camera_id, f"user_ids={ids}", request)
    db.commit()
    return {"camera_id": camera_id, "user_ids": ids}


@router.get("/officers/all")
def camera_officer_map(db: Session = Depends(get_db), user: User = Depends(operator_or_admin)):
    """{camera_id: [officer names]} for the Cameras and Map pages."""
    from backend.models.camera_officer import CameraOfficer
    out = {}
    rows = (db.query(CameraOfficer, User).join(User, User.id == CameraOfficer.user_id)
            .order_by(CameraOfficer.priority).all())
    for co, u in rows:
        out.setdefault(co.camera_id, []).append({"id": u.id, "name": u.username})
    return out
