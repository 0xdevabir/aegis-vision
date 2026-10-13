"""Zone editor API: roles, validation, audit, and delivery to the pipeline."""
import os
import sys
import types

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_review.db")
sys.modules.setdefault("face_recognition", types.ModuleType("face_recognition"))

from fastapi.testclient import TestClient  # noqa: E402

from backend.auth.auth import create_access_token, hash_password  # noqa: E402
from backend.db.database import Base, SessionLocal, engine, init_db  # noqa: E402
from backend.main import app  # noqa: E402
from backend.models.audit_log import AuditLog  # noqa: E402
from backend.models.camera import Camera  # noqa: E402
from backend.models.user import User  # noqa: E402

SQUARE = [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]]


def _hdr(db, name, role):
    u = User(username=name, email=f"{name}@x.io", hashed_password=hash_password("x"), role=role)
    db.add(u); db.commit()
    return {"Authorization": "Bearer " + create_access_token({"user_id": u.id, "role": role})}


def test_geometry_roundtrip_roles_validation_audit_and_pipeline_delivery():
    init_db()
    db = SessionLocal()
    db.add(Camera(camera_id="gate_1", name="Gate", active=True)); db.commit()
    sup, op = _hdr(db, "sup", "supervisor"), _hdr(db, "op", "operator")
    c = TestClient(app)
    body = {"zones": [{"name": "door", "type": "restricted", "polygon": SQUARE}],
            "lines": [{"name": "gate", "p1": [0.5, 0], "p2": [0.5, 1]}]}

    assert c.get("/api/v1/cameras/gate_1/geometry", headers=op).json()["configured"] is False
    assert c.put("/api/v1/cameras/gate_1/geometry", json=body, headers=op).status_code == 403
    assert c.put("/api/v1/cameras/nope/geometry", json=body, headers=sup).status_code == 404
    bad = c.put("/api/v1/cameras/gate_1/geometry", headers=sup,
                json={"zones": [{"name": "x", "polygon": [[0, 0], [1, 1]]}], "lines": []})
    assert bad.status_code == 422 and "3-" in bad.json()["detail"]

    ok = c.put("/api/v1/cameras/gate_1/geometry", json=body, headers=sup)
    assert ok.status_code == 200
    got = c.get("/api/v1/cameras/gate_1/geometry", headers=op).json()
    assert got["configured"] and got["zones"][0]["name"] == "door" and got["lines"][0]["name"] == "gate"
    assert db.query(AuditLog).filter(AuditLog.action == "GEOMETRY_CHANGE").count() == 1

    key = os.environ["INTERNAL_API_KEY"]
    r = c.get("/api/v1/config/runtime?camera_id=gate_1", headers={"X-Internal-Key": key}).json()
    assert r["geometry"]["zones"][0]["type"] == "restricted"
    assert c.get("/api/v1/config/runtime", headers={"X-Internal-Key": key}).json()["geometry"] is None
    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    try:
        os.remove("test_review.db")
    except OSError:
        pass
