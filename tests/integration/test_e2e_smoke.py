"""Smoke test: alert dispatch payload shape."""

import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_aegis_smoke.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only-32chars")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-32-chars!!")

from backend.utils.events import build_event_payload


def test_alert_payload_has_gps_fields():
    p = build_event_payload(
        event_type="CRIMINAL_DETECTED",
        severity="critical",
        camera_id="gate_1",
        camera_lat=23.81,
        camera_lng=90.41,
        person_name="TEST",
        message="test",
    )
    assert p["camera_lat"] == 23.81
    assert p["camera_lng"] == 90.41
    assert "maps_url" in p or p.get("data")
