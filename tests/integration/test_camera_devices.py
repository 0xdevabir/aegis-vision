"""Device list API: which connected camera is used by which registered camera."""
import os
import sys
import types

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_review.db")
sys.modules.setdefault("face_recognition", types.ModuleType("face_recognition"))

from fastapi.testclient import TestClient  # noqa: E402

from backend.auth.auth import create_access_token, hash_password  # noqa: E402
from backend.db.database import SessionLocal, init_db  # noqa: E402
from backend.main import app  # noqa: E402
from backend.models.camera import Camera  # noqa: E402
from backend.models.user import User  # noqa: E402
from utils.media import devices  # noqa: E402


def test_devices_show_new_bound_legacy_and_unplugged(monkeypatch):
    init_db()
    db = SessionLocal()
    db.query(Camera).filter(Camera.camera_id.like("dev_%")).delete(synchronize_session=False)
    db.query(User).filter(User.username == "dev_op").delete()
    db.add_all([
        Camera(camera_id="dev_bound", name="Bound", rtsp_url="device:uid-b", active=False),
        Camera(camera_id="dev_legacy", name="Legacy", rtsp_url="0", active=True),
        Camera(camera_id="dev_gone", name="Gone", rtsp_url="device:uid-gone", active=True),
        Camera(camera_id="dev_ip", name="IP", rtsp_url="rtsp://10.0.0.9/s", active=True),
        User(username="dev_op", email="dev_op@x.io", hashed_password=hash_password("x"), role="operator"),
    ])
    db.commit()
    uid = db.query(User).filter(User.username == "dev_op").one().id
    hdr = {"Authorization": "Bearer " + create_access_token({"user_id": uid, "role": "operator"})}
    monkeypatch.setattr(devices, "list_local_cameras", lambda: [
        {"index": 0, "name": "Built-in", "uid": "uid-a", "source": "device:uid-a"},
        {"index": 1, "name": "USB", "uid": "uid-b", "source": "device:uid-b"},
        {"index": 2, "name": "Just plugged in", "uid": "uid-c", "source": "device:uid-c"},
    ])
    try:
        body = TestClient(app).get("/api/v1/cameras/devices", headers=hdr).json()
        by_name = {d["name"]: d for d in body["devices"]}
        assert (by_name["Built-in"]["camera_id"], by_name["Built-in"]["bound"]) == ("dev_legacy", False)
        assert (by_name["USB"]["camera_id"], by_name["USB"]["bound"], by_name["USB"]["active"]) == ("dev_bound", True, False)
        assert by_name["Just plugged in"]["camera_id"] is None
        assert "dev_gone" in body["unplugged"]
        assert "dev_ip" not in body["unplugged"] and "dev_legacy" not in body["unplugged"]
    finally:
        db.query(Camera).filter(Camera.camera_id.like("dev_%")).delete(synchronize_session=False)
        db.query(User).filter(User.username == "dev_op").delete()
        db.commit()
        db.close()
