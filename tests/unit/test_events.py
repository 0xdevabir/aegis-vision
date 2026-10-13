"""Tests for live event payload builder."""

from backend.utils.events import build_event_payload


class TestBuildEventPayload:
    def test_criminal_event(self):
        payload = build_event_payload(
            event_type="CRIMINAL_DETECTED",
            severity="critical",
            camera_location="Gate_1",
            camera_id="gate_1",
            track_id=42,
            person_name="CRIMINAL_001_Sadik",
            message="Criminal detected",
        )
        assert payload["alert_type"] == "CRIMINAL_DETECTED"
        assert payload["severity"] == "critical"
        assert payload["person_name"] == "CRIMINAL_001_Sadik"
        assert payload["data"]["criminal_name"] == "CRIMINAL_001_Sadik"
        assert "timestamp" in payload

    def test_criminal_event_with_gps(self):
        payload = build_event_payload(
            event_type="CRIMINAL_DETECTED",
            severity="critical",
            camera_location="Main Gate",
            camera_id="gate_1",
            camera_lat=23.8103,
            camera_lng=90.4125,
            person_name="CRIMINAL_001_Sadik",
        )
        assert payload["camera_lat"] == 23.8103
        assert payload["camera_lng"] == 90.4125
        assert "google.com/maps" in payload["maps_url"]
        assert payload["data"]["camera_lat"] == 23.8103

