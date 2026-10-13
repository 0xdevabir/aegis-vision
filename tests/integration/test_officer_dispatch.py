"""A criminal alert on a camera is auto-assigned to that camera's police officer and SMSed to them."""
import asyncio
import os
import sys
import types

os.environ["DATABASE_URL"] = "sqlite:///./test_officer.db"
os.environ["USE_SQLITE"] = "false"
sys.modules.setdefault("face_recognition", types.ModuleType("face_recognition"))

from unittest.mock import AsyncMock, patch  # noqa: E402

from backend.db.database import Base, SessionLocal, engine, init_db  # noqa: E402
from backend.models.alert import Alert  # noqa: E402,F401
from backend.models.camera import Camera  # noqa: E402
from backend.models.camera_officer import CameraOfficer  # noqa: E402
from backend.models.incident import Incident  # noqa: E402
from backend.models.known_person import KnownPerson  # noqa: E402
from backend.models.user import User  # noqa: E402
from backend.services import alert_dispatcher as ad  # noqa: E402
from backend.services import officer_dispatch as od  # noqa: E402
from backend.utils import http_retry  # noqa: E402


def test_alert_routes_to_assigned_officer(monkeypatch):
    monkeypatch.setenv("ALERTS_ENABLED", "true")
    monkeypatch.setenv("SMS_WEBHOOK", "http://sms.test/send")
    init_db()
    db = SessionLocal()
    db.add_all([
        User(username="off1", email="o1@t", hashed_password="x", role="police", phone="+8801700000001"),
        User(username="off2", email="o2@t", hashed_password="x", role="police"),
        Camera(camera_id="gate_a", name="Gate A", lat=23.8, lng=90.4),
        Camera(camera_id="gate_b", name="Gate B", lat=23.9, lng=90.5),
        KnownPerson(person_id="X", name="Test Crook", category="criminal", criminal_status="wanted"),
    ])
    db.commit()
    o1 = db.query(User).filter(User.username == "off1").first()
    db.add(CameraOfficer(camera_id="gate_a", user_id=o1.id, priority=0))
    db.commit()
    db.close()

    loop = asyncio.get_event_loop_policy().new_event_loop()
    posted = []

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, timeout=None):
            posted.append((url, json))
            return types.SimpleNamespace(status_code=200)

    with patch.object(ad, "broadcast_live_event", new=AsyncMock(side_effect=lambda **kw: dict(kw.get("extra") or {}))), \
         patch.object(ad.manager, "broadcast", new=AsyncMock()), \
         patch.object(od.httpx, "AsyncClient", FakeClient):
        monkeypatch.setenv("ALERT_DEDUPE_SECONDS", "0")
        res = loop.run_until_complete(ad.dispatch_alert(
            alert_type="CRIMINAL_DETECTED", severity="critical", person_name="X",
            camera_id="gate_a", camera_location="Gate A"))
        assert [o["name"] for o in res["payload"]["assigned_officers"]] == ["off1"]
        assert len(posted) == 1 and posted[0][1]["to"] == "+8801700000001"
        assert "Test Crook" not in posted[0][1]["message"] or "unverified" in posted[0][1]["message"]
        assert "23.80000,90.40000" in posted[0][1]["message"]            # camera coordinates

        db = SessionLocal()
        inc = db.query(Incident).filter(Incident.alert_id == res["alert_id"]).first()
        assert inc.assigned_name == "off1"
        db.close()

        # a camera with no officer: alert still raised, nobody paged
        posted.clear()
        res2 = loop.run_until_complete(ad.dispatch_alert(
            alert_type="CRIMINAL_DETECTED", severity="critical", person_name="X", camera_id="gate_b"))
        assert res2["payload"]["assigned_officers"] == [] and posted == []
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_retry_helper_retries_then_succeeds_and_reports_failure():
    calls = []

    class Flaky:
        async def post(self, url, json=None, timeout=None):
            calls.append(1)
            return types.SimpleNamespace(status_code=503 if len(calls) < 3 else 200)

    loop = asyncio.get_event_loop_policy().new_event_loop()
    assert loop.run_until_complete(http_retry.post_with_retry(Flaky(), "http://x", {}, backoff=0)) is True
    assert len(calls) == 3

    class Dead:
        async def post(self, url, json=None, timeout=None):
            return types.SimpleNamespace(status_code=500)

    assert loop.run_until_complete(http_retry.post_with_retry(Dead(), "http://x", {}, backoff=0)) is False


def test_dedupe_then_escalation_pages_backup_once(monkeypatch):
    from datetime import datetime, timedelta

    from backend.services import escalation
    monkeypatch.setenv("ALERTS_ENABLED", "true")
    monkeypatch.setenv("SMS_WEBHOOK", "http://sms.test/send")
    monkeypatch.setenv("ALERT_DEDUPE_SECONDS", "120")
    init_db()
    db = SessionLocal()
    db.add_all([
        User(username="p1", email="p1@t", hashed_password="x", role="police", phone="+8801700000011"),
        User(username="p2", email="p2@t", hashed_password="x", role="police", phone="+8801700000012"),
        Camera(camera_id="cam_e", name="Cam E", lat=1.0, lng=2.0),
        KnownPerson(person_id="Z", name="Z Crook", category="criminal", criminal_status="wanted"),
    ])
    db.commit()
    for prio, name in enumerate(["p1", "p2"]):
        db.add(CameraOfficer(camera_id="cam_e", priority=prio, user_id=db.query(User).filter(User.username == name).first().id))
    db.commit()
    db.close()

    posted = []

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, timeout=None):
            posted.append(json)
            return types.SimpleNamespace(status_code=200)

    loop = asyncio.get_event_loop_policy().new_event_loop()
    with patch.object(ad, "broadcast_live_event", new=AsyncMock(side_effect=lambda **kw: dict(kw.get("extra") or {}))), \
         patch.object(ad.manager, "broadcast", new=AsyncMock()), \
         patch.object(escalation.manager, "broadcast", new=AsyncMock()), \
         patch.object(od.httpx, "AsyncClient", FakeClient):
        first = loop.run_until_complete(ad.dispatch_alert(
            alert_type="CRIMINAL_DETECTED", severity="critical", person_name="Z", camera_id="cam_e"))
        again = loop.run_until_complete(ad.dispatch_alert(
            alert_type="CRIMINAL_DETECTED", severity="critical", person_name="Z", camera_id="cam_e"))
        assert again["status"] == "deduplicated" and again["alert_id"] == first["alert_id"]
        assert len(posted) == 2                       # initial page went to both officers, none for the duplicate

        posted.clear()
        db = SessionLocal()
        assert loop.run_until_complete(escalation.escalate_unacknowledged(db, 120)) == 0          # too early
        later = datetime.utcnow() + timedelta(seconds=300)
        assert loop.run_until_complete(escalation.escalate_unacknowledged(db, 120, now=later)) == 1
        assert [p["officer"] for p in posted] == ["p2"] and "ESCALATION" in posted[0]["message"]
        assert db.query(Alert).get(first["alert_id"]).escalated_at is not None
        assert loop.run_until_complete(escalation.escalate_unacknowledged(db, 120, now=later)) == 0  # only once
        db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
