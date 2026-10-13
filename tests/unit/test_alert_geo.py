"""Tests for alert event payload geo fields."""

from backend.utils.events import build_event_payload


class TestAlertGeoPayload:
    def test_includes_gps_and_maps_url(self):
        payload = build_event_payload(
            event_type="CRIMINAL_DETECTED",
            severity="critical",
            camera_id="gate_1",
            camera_lat=23.8103,
            camera_lng=90.4125,
            camera_name="Main Gate",
            person_name="CRIMINAL_001",
        )
        assert payload["camera_lat"] == 23.8103
        assert payload["camera_lng"] == 90.4125
        assert "google.com/maps" in payload["maps_url"]
        assert payload["data"]["camera_lat"] == 23.8103
