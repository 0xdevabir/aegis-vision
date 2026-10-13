"""Watchlist alerts hold external webhooks until an operator confirms."""
import asyncio
import os
import sys
import types

os.environ["DATABASE_URL"] = "sqlite:///./test_review.db"
os.environ["USE_SQLITE"] = "false"
sys.modules.setdefault("face_recognition", types.ModuleType("face_recognition"))

from unittest.mock import AsyncMock, patch  # noqa: E402

from backend.db.database import Base, SessionLocal, engine, init_db  # noqa: E402
from backend.models.known_person import KnownPerson  # noqa: E402
from backend.models.user import User  # noqa: E402
from backend.services import alert_dispatcher as ad  # noqa: E402


def test_criminal_alert_holds_webhooks_then_releases(monkeypatch):
    monkeypatch.setenv("ALERT_DEDUPE_SECONDS", "0")      # this test dispatches the same type repeatedly
    init_db()
    _db = SessionLocal()
    _db.add(KnownPerson(person_id="X", name="Test Crook", category="criminal", criminal_status="wanted"))
    _db.add(KnownPerson(person_id="C", name="Civ", category="civilian", criminal_status="cleared"))
    _db.commit()
    _db.close()
    ok = asyncio.get_event_loop_policy().new_event_loop()
    with patch.object(ad, "_send_webhooks", new=AsyncMock(return_value="law_enforcement")) as sw, \
         patch.object(ad, "broadcast_live_event", new=AsyncMock(return_value={})), \
         patch.object(ad.manager, "broadcast", new=AsyncMock()):
        res = ok.run_until_complete(ad.dispatch_alert(
            alert_type="CRIMINAL_DETECTED", severity="critical", person_name="X"))
        sw.assert_not_called()
        rejected = ok.run_until_complete(ad.dispatch_alert(
            alert_type="CRIMINAL_DETECTED", severity="critical", person_name="C"))
        assert rejected["status"] == "rejected"
        db = SessionLocal()
        from backend.models.alert import Alert
        a = db.query(Alert).get(res["alert_id"])
        assert a.review_status == "pending" and "law" not in (a.channels_sent or "")
        assert "unverified" in a.message
        ok.run_until_complete(ad.release_held_webhooks(a))
        sw.assert_called_once()
        db.close()
        # non-identification alert is not held
        ok.run_until_complete(ad.dispatch_alert(alert_type="WEAPON_DETECTED", severity="critical"))
        assert sw.call_count == 2
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    try:
        os.remove("test_review.db")
    except OSError:
        pass


def test_events_search_filters_by_type_camera_and_time():
    import sys, types  # noqa: E401
    sys.modules.setdefault("face_recognition", types.ModuleType("face_recognition"))
    from datetime import datetime, timedelta
    from fastapi.testclient import TestClient
    from backend.auth.auth import create_access_token, hash_password
    from backend.main import app
    from backend.services.event_store import record_event

    init_db()
    db = SessionLocal()
    u = User(username="op", email="op@x.io", hashed_password=hash_password("x"), role="operator")
    db.add(u); db.commit()
    record_event(db, "WEAPON_DETECTED", "critical", camera_id="cam3", track_id=7, confidence=0.8)
    record_event(db, "INTRUSION", "high", camera_id="cam1", zone="door")
    hdr = {"Authorization": "Bearer " + create_access_token({"user_id": u.id, "role": u.role})}
    c = TestClient(app)
    r = c.get("/api/v1/events/search?event_type=weapon_detected&camera_id=cam3", headers=hdr).json()
    assert len(r) == 1 and r[0]["track_id"] == 7 and r[0]["confidence"] == 0.8
    assert c.get("/api/v1/events/search?zone=door", headers=hdr).json()[0]["event_type"] == "INTRUSION"
    future = (datetime.utcnow() + timedelta(days=1)).isoformat()
    assert c.get(f"/api/v1/events/search?since={future}", headers=hdr).json() == []
    assert c.get("/api/v1/events/search").status_code == 401
    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    try:
        os.remove("test_review.db")
    except OSError:
        pass


def test_thresholds_validated_audited_and_served_to_pipeline():
    import sys, types  # noqa: E401
    sys.modules.setdefault("face_recognition", types.ModuleType("face_recognition"))
    from fastapi.testclient import TestClient
    from backend.auth.auth import create_access_token, hash_password
    from backend.main import app
    from backend.models.audit_log import AuditLog

    init_db()
    db = SessionLocal()
    admin = User(username="adm", email="a@x.io", hashed_password=hash_password("x"), role="admin")
    db.add(admin); db.commit()
    hdr = {"Authorization": "Bearer " + create_access_token({"user_id": admin.id, "role": "admin"})}
    c = TestClient(app)
    ok = c.put("/api/v1/config/threshold.face_tolerance", json={"value": "0.40"}, headers=hdr)
    assert ok.status_code == 200
    assert c.put("/api/v1/config/threshold.face_tolerance", json={"value": "0.99"}, headers=hdr).status_code == 400
    assert c.put("/api/v1/config/threshold.bogus", json={"value": "1"}, headers=hdr).status_code == 400
    assert db.query(AuditLog).filter(AuditLog.action == "CONFIG_CHANGE").count() == 1
    key = os.environ["INTERNAL_API_KEY"]
    r = c.get("/api/v1/config/runtime", headers={"X-Internal-Key": key})
    assert r.status_code == 200 and r.json()["face_tolerance"] == 0.40
    assert c.get("/api/v1/config/runtime").status_code == 401
    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    try:
        os.remove("test_review.db")
    except OSError:
        pass


def test_trends_endpoint_works_on_sqlite():
    import sys, types  # noqa: E401
    sys.modules.setdefault("face_recognition", types.ModuleType("face_recognition"))
    from fastapi.testclient import TestClient
    from backend.auth.auth import create_access_token, hash_password
    from backend.main import app
    from backend.models.evidence import Evidence

    init_db()
    db = SessionLocal()
    u = User(username="tr", email="t@x.io", hashed_password=hash_password("x"), role="operator")
    db.add(u); db.add(Evidence(camera_location="Gate", track_id=1, category="suspicious"))
    db.commit()
    hdr = {"Authorization": "Bearer " + create_access_token({"user_id": u.id, "role": u.role})}
    r = TestClient(app).get("/api/v1/analytics/trends?days=7", headers=hdr)
    assert r.status_code == 200 and r.json()[0]["events"] == 1
    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    try:
        os.remove("test_review.db")
    except OSError:
        pass
