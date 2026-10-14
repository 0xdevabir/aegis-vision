"""Cameras start on standby and are switched on/off one by one from the Live page."""

import os

import yaml
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_camera_power.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only-32chars")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-32-chars!!")
os.environ.setdefault("ENVIRONMENT", "development")

from backend.main import app  # noqa: E402
from backend.api import camera_routes  # noqa: E402
from backend.db.database import SessionLocal, init_db  # noqa: E402
from backend.models.user import User  # noqa: E402

client = TestClient(app)


def _auth(role):
    from backend.auth.auth import hash_password, issue_token

    name = f"power_{role}"
    db = SessionLocal()
    user = db.query(User).filter(User.username == name).first()
    if not user:
        user = User(username=name, email=f"{name}@t.local", hashed_password=hash_password("pass1234"),
                    role=role, is_active=True)
        db.add(user)
        db.commit()
    token = issue_token(user)       # logins are rate limited across the test run
    db.close()
    return {"Authorization": f"Bearer {token}"}


def test_operator_starts_and_stops_a_camera(tmp_path, monkeypatch):
    init_db()
    path = tmp_path / "cameras.yaml"
    path.write_text(yaml.safe_dump({"cameras": [
        {"id": "laptop", "source": "0", "enabled": True, "started": False},
        {"id": "paused", "source": "1", "enabled": False, "started": False},
    ]}))
    monkeypatch.setattr(camera_routes, "CAMERAS_YAML", path)
    op = _auth("operator")

    assert client.get("/api/v1/cameras/power", headers=op).json() == {"laptop": False, "paused": False}

    r = client.post("/api/v1/cameras/laptop/power", json={"on": True}, headers=op)
    assert r.status_code == 200 and r.json()["laptop"] is True
    saved = yaml.safe_load(path.read_text())["cameras"][0]
    assert saved["started"] is True and saved["source"] == "0"

    assert client.post("/api/v1/cameras/laptop/power", json={"on": False}, headers=op).json()["laptop"] is False
    assert client.post("/api/v1/cameras/paused/power", json={"on": True}, headers=op).status_code == 409
    assert client.post("/api/v1/cameras/nope/power", json={"on": True}, headers=op).status_code == 404
    assert client.post("/api/v1/cameras/laptop/power", json={"on": True}, headers=_auth("police")).status_code == 403
    assert client.post("/api/v1/cameras/laptop/power", json={"on": True}).status_code == 401


def test_added_camera_runs_and_deleted_camera_stays_deleted(tmp_path, monkeypatch):
    init_db()
    path = tmp_path / "cameras.yaml"
    path.write_text(yaml.safe_dump({"cameras": [{"id": "laptop", "source": "0", "enabled": True}]}))
    monkeypatch.setattr(camera_routes, "CAMERAS_YAML", path)
    admin = _auth("admin")
    ids = lambda: {c["camera_id"]: c["active"] for c in client.get("/api/v1/cameras/", headers=admin).json()}

    r = client.post("/api/v1/cameras/", json={"camera_id": "door_cam", "name": "Door",
                                              "rtsp_url": "http://10.0.0.5:8080/video"}, headers=admin)
    assert r.status_code == 200
    assert "door_cam" in {c["id"] for c in yaml.safe_load(path.read_text())["cameras"]}
    assert ids()["door_cam"] is True

    assert client.delete("/api/v1/cameras/door_cam", headers=admin).status_code == 200
    assert [c["id"] for c in yaml.safe_load(path.read_text())["cameras"]] == ["laptop"]
    assert "door_cam" not in ids()          # listing used to copy the leftover yaml entry back


def test_camera_missing_from_yaml_is_not_shown_as_live(tmp_path, monkeypatch):
    from backend.models.camera import Camera
    init_db()
    path = tmp_path / "cameras.yaml"
    path.write_text(yaml.safe_dump({"cameras": []}))
    monkeypatch.setattr(camera_routes, "CAMERAS_YAML", path)
    db = SessionLocal()
    if not db.query(Camera).filter(Camera.camera_id == "orphan").first():
        db.add(Camera(camera_id="orphan", name="Orphan", rtsp_url="5", active=True))
        db.commit()
    db.close()
    admin = _auth("admin")
    cams = {c["camera_id"]: c["active"] for c in client.get("/api/v1/cameras/", headers=admin).json()}
    assert cams["orphan"] is False
    assert client.delete("/api/v1/cameras/orphan", headers=admin).status_code == 200
