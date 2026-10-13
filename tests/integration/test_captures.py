"""Capture basket API: the pipeline uploads a still for a live red alert, operators read it back."""

import os

import cv2
import numpy as np
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_captures.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only-32chars")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-32-chars!!")
os.environ.setdefault("ENVIRONMENT", "development")

from backend.main import app  # noqa: E402
from backend.api import capture_routes  # noqa: E402
from backend.db.database import SessionLocal, init_db  # noqa: E402
from backend.models.alert import Alert  # noqa: E402
from backend.models.user import User  # noqa: E402

client = TestClient(app)
KEY = {"X-Internal-Key": os.environ["INTERNAL_API_KEY"]}


def _jpeg():
    ok, buf = cv2.imencode(".jpg", np.full((400, 160, 3), 90, np.uint8))
    assert ok
    return buf.tobytes()


def _token():
    from backend.auth.auth import hash_password

    db = SessionLocal()
    if not db.query(User).filter(User.username == "capop").first():
        db.add(User(username="capop", email="cap@t.local", hashed_password=hash_password("pass1234"),
                    role="operator", is_active=True))
        db.commit()
    db.close()
    return client.post("/api/v1/auth/login", json={"username": "capop", "password": "pass1234"}).json()["access_token"]


def _ingest(camera_id, **extra):
    data = {"camera_id": camera_id, "alert_type": "WEAPON_DETECTED", "track_id": "7",
            "camera_location": "Gate", "camera_lat": "23.8103", "camera_lng": "90.4125",
            "bbox": "0.1000,0.2000,0.3000,0.5000", **extra}
    return client.post("/api/v1/captures/ingest", data=data, headers=KEY,
                       files={"file": ("capture.jpg", _jpeg(), "image/jpeg")})


def test_capture_is_stored_for_a_live_red_alert_and_served_back():
    init_db()
    db = SessionLocal()
    alert = Alert(alert_type="WEAPON_DETECTED", severity="critical", camera_id="cap_cam_1", track_id=7)
    db.add(alert)
    db.commit()
    alert_id = alert.id
    db.close()

    r = _ingest("cap_cam_1")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "stored"
    assert r.json()["alert_id"] == alert_id

    token = _token()
    items = client.get(f"/api/v1/captures/?alert_id={alert_id}", headers={"Authorization": f"Bearer {token}"}).json()
    assert len(items) == 1
    item = items[0]
    assert item["camera_id"] == "cap_cam_1"
    assert item["bbox"] == [0.1, 0.2, 0.3, 0.5]
    assert item["maps_url"].endswith("23.8103,90.4125")
    assert (item["width"], item["height"]) == (160, 400)
    assert len(item["content_sha256"]) == 64

    img = client.get(f"/api/v1/captures/{item['id']}/image?token={token}")
    assert img.status_code == 200
    assert img.content[:2] == b"\xff\xd8"
    assert client.get(f"/api/v1/captures/{item['id']}/image").status_code == 401


def test_no_capture_without_a_red_alert(monkeypatch):
    init_db()
    monkeypatch.setattr(capture_routes.time, "sleep", lambda s: None)
    r = _ingest("cap_cam_without_alert")
    assert r.status_code == 200
    assert r.json()["status"] == "no_alert"


def test_ingest_needs_the_internal_key_and_a_real_image():
    init_db()
    r = client.post("/api/v1/captures/ingest", data={"camera_id": "c", "alert_type": "WEAPON_DETECTED"},
                    files={"file": ("capture.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 401
    r = client.post("/api/v1/captures/ingest", data={"camera_id": "c", "alert_type": "WEAPON_DETECTED"},
                    headers=KEY, files={"file": ("capture.jpg", b"not an image", "image/jpeg")})
    assert r.status_code == 400
    assert client.get("/api/v1/captures/").status_code == 401
