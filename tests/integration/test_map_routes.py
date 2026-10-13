"""Map API: all cameras (incl. off / no GPS) and alert-based events placed by camera."""
import json
import os
import sys
import types

from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_aegis_api.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only-32chars")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-32-chars!!")
os.environ.setdefault("ENVIRONMENT", "development")
sys.modules.setdefault("face_recognition", types.ModuleType("face_recognition"))

from backend.auth.auth import create_access_token, hash_password  # noqa: E402
from backend.db.database import SessionLocal, init_db  # noqa: E402
from backend.main import app  # noqa: E402
from backend.middleware.rate_limiter import _limiter  # noqa: E402
from backend.models.alert import Alert  # noqa: E402
from backend.models.camera import Camera  # noqa: E402
from backend.models.user import User  # noqa: E402

client = TestClient(app)


def test_map_lists_all_cameras_and_places_alerts():
    init_db()
    _limiter._buckets.clear()
    db = SessionLocal()
    db.query(Camera).filter(Camera.camera_id.like("mp_%")).delete(synchronize_session=False)
    db.query(Alert).filter(Alert.camera_id.like("mp_%")).delete(synchronize_session=False)
    db.query(User).filter(User.username == "mp_op").delete()
    u = User(username="mp_op", email="mp_op@t.local", hashed_password=hash_password("OperPass1234"), role="operator", is_active=True)
    db.add_all([
        u,
        Camera(camera_id="mp_on", name="On", lat=23.8, lng=90.4, active=True, heading=90, fov=70, range_m=40),
        Camera(camera_id="mp_off", name="Off", lat=23.9, lng=90.5, active=False),
        Camera(camera_id="mp_nogps", name="NoGps", active=True),
    ])
    db.flush()
    db.add_all([
        Alert(alert_type="CRIMINAL_DETECTED", severity="critical", camera_id="mp_on", message="Match | extra",
              details=json.dumps({"lat": 23.81, "lng": 90.41}), review_status="pending"),
        Alert(alert_type="WEAPON_DETECTED", severity="critical", camera_id="mp_off", message="Weapon", review_status="not_required"),
        Alert(alert_type="PIPELINE_HEARTBEAT", severity="info", camera_id="mp_on", message="hb", review_status="not_required"),
        Alert(alert_type="CRIMINAL_DETECTED", severity="critical", camera_id="mp_on", message="Rejected", review_status="rejected"),
    ])
    db.commit()
    uid = u.id
    db.close()
    h = {"Authorization": f"Bearer {create_access_token({'user_id': uid, 'role': 'operator'})}"}

    cams = {c["camera_id"]: c for c in client.get("/api/v1/map/cameras", headers=h).json()}
    assert {"mp_on", "mp_off", "mp_nogps"} <= set(cams)                       # off and no-GPS cameras are included
    assert cams["mp_on"]["heading"] == 90 and cams["mp_nogps"]["lat"] is None

    ev = [e for e in client.get("/api/v1/map/events?hours=1", headers=h).json() if (e["camera_id"] or "").startswith("mp_")]
    types_ = sorted(e["event_type"] for e in ev)
    assert types_ == ["CRIMINAL_DETECTED", "WEAPON_DETECTED"]                 # heartbeat and rejected alerts hidden
    crim = next(e for e in ev if e["event_type"] == "CRIMINAL_DETECTED")
    assert (crim["lat"], crim["lng"]) == (23.81, 90.41) and crim["description"] == "Match"   # position stored with the alert
    weap = next(e for e in ev if e["event_type"] == "WEAPON_DETECTED")
    assert (weap["lat"], weap["lng"]) == (23.9, 90.5)                         # falls back to the camera's position
    only = client.get("/api/v1/map/events?hours=1&types=WEAPON_DETECTED", headers=h).json()
    assert {e["event_type"] for e in only} == {"WEAPON_DETECTED"}
