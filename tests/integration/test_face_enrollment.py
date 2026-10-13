"""Face enrollment + verification API (dlib replaced by a deterministic fake)."""

import os
import types

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_aegis_api.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only-32chars")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-32-chars!!")
os.environ.setdefault("ENVIRONMENT", "development")

from backend.main import app  # noqa: E402
from backend.services import face_service  # noqa: E402

_real_check = face_service._check_quality   # the autouse fixture stubs the module attribute

client = TestClient(app)


def _fake_engine():
    """One 'face' per image; embedding = mean brightness, so equal images match."""
    def locations(rgb, **_):
        if rgb.mean() < 5:  # black image -> no face
            return []
        h, w = rgb.shape[:2]
        return [(0, w, h, 0)] * (2 if rgb[0, 0, 0] == 7 else 1)

    def encodings(rgb, boxes, **_):
        return [np.full(128, float(rgb.mean()) / 255.0) for _ in boxes]

    mod = types.SimpleNamespace(face_locations=locations, face_encodings=encodings)
    return lambda: mod


def _clean_faces():
    """The SQLite test DB persists between runs; start every test from an empty registry."""
    from backend.db.database import SessionLocal
    from backend.models.evidence import Evidence
    from backend.models.face_encoding import FaceEncoding
    from backend.models.known_person import KnownPerson
    from backend.models.person_image import PersonImage
    db = SessionLocal()
    try:
        db.query(Evidence).update({Evidence.person_id: None})
        for m in (FaceEncoding, PersonImage, KnownPerson):
            db.query(m).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    from backend.db.database import init_db
    init_db()
    _clean_faces()
    monkeypatch.setattr(face_service, "_engine", _fake_engine())
    monkeypatch.setattr(face_service, "get_tolerance", lambda: 0.45)
    monkeypatch.setattr(face_service, "_check_quality", lambda *_: None)   # fake images are flat gray


def _login(username: str, role: str) -> dict:
    from backend.auth.auth import hash_password
    from backend.db.database import SessionLocal
    from backend.models.user import User
    db = SessionLocal()
    if not db.query(User).filter(User.username == username).first():
        db.add(User(username=username, email=f"{username}@t.local",
                    hashed_password=hash_password("pass1234"), role=role, is_active=True))
        db.commit()
    db.close()
    r = client.post("/api/v1/auth/login", json={"username": username, "password": "pass1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _img(gray: int, fmt=".png") -> bytes:
    ok, buf = cv2.imencode(fmt, np.full((64, 64, 3), gray, np.uint8))
    assert ok
    return buf.tobytes()


def _enroll(headers, name, gray, **extra):
    return client.post("/api/v1/faces/persons", headers=headers,
                       data={"name": name, "category": "criminal", "criminal_status": "wanted",
                             "threat_level": "6", **extra},
                       files=[("files", ("a.png", _img(gray), "image/png"))])


def test_enroll_then_verify_match_and_no_match():
    sup = _login("face_sup", "supervisor")
    r = _enroll(sup, "Alice Target", 120)
    assert r.status_code == 201, r.text
    pid = r.json()["person"]["person_id"]
    assert r.json()["person"]["encoding_count"] == 1

    ok = client.post("/api/v1/faces/verify", headers=sup,
                     files={"file": ("p.png", _img(120), "image/png")})
    body = ok.json()
    assert body["status"] == "match"
    assert body["best_match"]["person_id"] == pid
    assert body["best_match"]["distance"] == 0

    miss = client.post("/api/v1/faces/verify", headers=sup,
                       files={"file": ("p.png", _img(200), "image/png")})
    assert miss.json()["status"] == "no_match"
    assert miss.json()["best_match"] is None

    # 1:1 mode against the specific record
    one = client.post("/api/v1/faces/verify", headers=sup, data={"person_id": pid},
                      files={"file": ("p.png", _img(120), "image/png")})
    assert one.json()["mode"] == "1:1" and one.json()["status"] == "match"


def test_verify_no_face_and_bad_image():
    op = _login("face_op", "operator")
    r = client.post("/api/v1/faces/verify", headers=op,
                    files={"file": ("p.png", _img(0), "image/png")})
    assert r.json()["status"] == "no_face"
    bad = client.post("/api/v1/faces/verify", headers=op,
                      files={"file": ("p.txt", b"not an image", "text/plain")})
    assert bad.status_code == 415


def test_enroll_rejects_no_face_and_multiple_faces():
    sup = _login("face_sup", "supervisor")
    assert _enroll(sup, "Nobody", 0).status_code == 422
    r = _enroll(sup, "Crowd", 7)
    assert r.status_code == 422
    assert "faces detected" in r.json()["detail"]["results"][0]["reason"]


def test_enroll_flags_duplicate_and_rbac():
    sup = _login("face_sup", "supervisor")
    op = _login("face_op", "operator")
    assert _enroll(op, "Nope", 90).status_code == 403
    first = _enroll(sup, "Original", 90).json()["person"]["person_id"]
    dup = _enroll(sup, "Copycat", 90).json()
    assert dup["results"][0]["possible_duplicate_of"][0]["person_id"] == first


def test_image_lifecycle_and_delete():
    sup = _login("face_sup", "supervisor")
    admin = _login("face_admin", "admin")
    p = _enroll(sup, "Lifecycle", 60).json()["person"]
    pid = p["person_id"]
    added = client.post(f"/api/v1/faces/persons/{pid}/images", headers=sup,
                        files=[("files", ("b.png", _img(61), "image/png"))])
    assert added.json()["person"]["image_count"] == 2
    detail = client.get(f"/api/v1/faces/persons/{pid}", headers=sup).json()
    first_img = detail["images"][0]["id"]

    token = sup["Authorization"].split()[1]
    img = client.get(f"/api/v1/faces/images/{first_img}?token={token}")
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/v1/faces/images/{first_img}").status_code == 401

    assert client.delete(f"/api/v1/faces/images/{first_img}", headers=sup).status_code == 200
    after = client.get(f"/api/v1/faces/persons/{pid}", headers=sup).json()
    assert after["image_count"] == 1 and after["encoding_count"] == 1
    last = after["images"][0]["id"]
    assert client.delete(f"/api/v1/faces/images/{last}", headers=sup).status_code == 409

    assert client.delete(f"/api/v1/faces/persons/{pid}", headers=sup).status_code == 403
    assert client.delete(f"/api/v1/faces/persons/{pid}", headers=admin).status_code == 200
    assert client.get(f"/api/v1/faces/persons/{pid}", headers=sup).status_code == 404


def test_update_person_validates():
    sup = _login("face_sup", "supervisor")
    _check_explicit_category(sup)
    pid = _enroll(sup, "Editable", 30).json()["person"]["person_id"]
    ok = client.patch(f"/api/v1/faces/persons/{pid}", headers=sup,
                      json={"criminal_status": "cleared", "threat_level": 1})
    assert ok.json()["criminal_status"] == "cleared"
    bad = client.patch(f"/api/v1/faces/persons/{pid}", headers=sup, json={"category": "alien"})
    assert bad.status_code == 422


def _add_evidence(gray, recorded_name=None, encrypted=False, with_roi=True):
    from backend.db.database import SessionLocal
    from backend.models.evidence import Evidence
    db = SessionLocal()
    try:
        ok, buf = cv2.imencode(".jpg", np.full((64, 64, 3), gray, np.uint8))
        blob = buf.tobytes()
        ev = Evidence(camera_location="test", track_id=1, person_name=recorded_name, is_criminal=False,
                      weapon_present=False, is_suspicious=True, category="suspicious",
                      frame_data=blob, roi_data=blob if with_roi else None, encrypted=encrypted)
        db.add(ev)
        db.commit()
        return ev.id
    finally:
        db.close()


def test_verify_evidence_match_and_no_match_and_agreement():
    sup = _login("face_sup", "supervisor")
    pid = _enroll(sup, "Evidence Target", 150).json()["person"]["person_id"]

    hit = client.post(f"/api/v1/faces/verify-evidence/{_add_evidence(150, recorded_name=pid)}", headers=sup).json()
    assert hit["status"] == "match" and hit["best_match"]["person_id"] == pid
    assert hit["source"] == "subject crop" and hit["agrees_with_live_id"] is True

    disagree = client.post(f"/api/v1/faces/verify-evidence/{_add_evidence(150, recorded_name='SOMEONE_ELSE')}",
                           headers=sup).json()
    assert disagree["status"] == "match" and disagree["agrees_with_live_id"] is False

    miss = client.post(f"/api/v1/faces/verify-evidence/{_add_evidence(220)}", headers=sup).json()
    assert miss["status"] == "no_match" and miss["agrees_with_live_id"] is None

    # no usable face in the crop -> falls back to the full frame, then reports no_face
    none = client.post(f"/api/v1/faces/verify-evidence/{_add_evidence(0)}", headers=sup).json()
    assert none["status"] == "no_face"

    assert client.post("/api/v1/faces/verify-evidence/999999", headers=sup).status_code == 404


def test_quality_gate_rejects_small_and_blurry_faces():
    flat = np.full((200, 200, 3), 128, np.uint8)
    with pytest.raises(face_service.FaceError, match="too small"):
        _real_check(flat, (0, 20, 20, 0))
    with pytest.raises(face_service.FaceError, match="blurry"):
        _real_check(flat, (0, 150, 150, 0))


def _check_explicit_category(sup):
    r = client.post("/api/v1/faces/persons", headers=sup, data={"name": "N"},
                    files=[("files", ("a.png", _img(100), "image/png"))])
    assert r.status_code == 422                       # category is required, no silent 'criminal'
    r = client.post("/api/v1/faces/persons", headers=sup,
                    data={"name": "N", "category": "civilian", "criminal_status": "wanted"},
                    files=[("files", ("a.png", _img(100), "image/png"))])
    assert r.status_code == 422                       # civilian can't be 'wanted'
