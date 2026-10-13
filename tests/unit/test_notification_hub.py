"""Tests for automated notification hub."""

import time
from unittest.mock import patch, MagicMock
from utils.alerts import NotificationHub


class TestNotificationHub:
    def test_criminal_throttle_per_track(self):
        hub = NotificationHub(alarm_interval=5.0)
        alarm = MagicMock()
        hub.alarm_callback = alarm

        with patch("utils.alerts.notification_hub.dispatch_alert") as mock_dispatch:
            now = time.time()
            hub.criminal_detected("CRIMINAL_001", "Gate", "gate_1", 1, now)
            hub.criminal_detected("CRIMINAL_001", "Gate", "gate_1", 1, now + 1)

            assert mock_dispatch.call_count == 1
            assert alarm.call_count == 1

    def test_different_cameras_both_fire(self):
        hub = NotificationHub(alarm_interval=5.0)
        with patch("utils.alerts.notification_hub.dispatch_alert") as mock_dispatch:
            now = time.time()
            hub.criminal_detected("A", "Gate", "cam_1", 1, now)
            hub.criminal_detected("A", "Lobby", "cam_2", 2, now + 0.1)
            assert mock_dispatch.call_count == 2

    def test_dispatch_payload(self):
        hub = NotificationHub()
        with patch("utils.alerts.notification_hub.dispatch_alert") as mock_dispatch:
            hub.criminal_detected("CRIMINAL_001_Sadik", "Main Gate", "gate_1", 5, time.time())
            mock_dispatch.assert_called_once()
            kwargs = mock_dispatch.call_args[1]
            assert kwargs["alert_type"] == "CRIMINAL_DETECTED"
            assert kwargs["severity"] == "critical"
            assert kwargs["camera_id"] == "gate_1"
            assert kwargs["person_name"] == "CRIMINAL_001_Sadik"
