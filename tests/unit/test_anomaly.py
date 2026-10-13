"""
Unit Tests — Anomaly Detector
================================
Tests for zone-based anomaly detection.
"""

from unittest.mock import MagicMock
from core.analysis.anomaly_detector import AnomalyDetector


def _make_track(track_id, cx, cy, confirmed=True):
    """Create a mock track object."""
    track = MagicMock()
    track.track_id = track_id
    track.is_confirmed.return_value = confirmed
    track.to_ltrb.return_value = (cx - 20, cy - 40, cx + 20, cy + 40)
    return track


class TestAnomalyDetector:
    def test_no_tracks_no_anomalies(self):
        detector = AnomalyDetector()
        anomalies = detector.update([], (480, 640, 3))
        assert anomalies == []

    def test_crowd_detection(self):
        """5+ people in one zone should trigger a crowd anomaly."""
        detector = AnomalyDetector(crowd_threshold=3)
        # Place 4 tracks in top-left quadrant (cx < 320, cy < 240)
        tracks = [_make_track(i, 100, 100) for i in range(4)]
        anomalies = detector.update(tracks, (480, 640, 3))
        crowd_anomalies = [a for a in anomalies if a["type"] == "crowd"]
        assert len(crowd_anomalies) >= 1
        assert crowd_anomalies[0]["zone"] == "top_left"

    def test_no_crowd_below_threshold(self):
        detector = AnomalyDetector(crowd_threshold=5)
        tracks = [_make_track(i, 100, 100) for i in range(3)]
        anomalies = detector.update(tracks, (480, 640, 3))
        crowd_anomalies = [a for a in anomalies if a["type"] == "crowd"]
        assert len(crowd_anomalies) == 0

    def test_unconfirmed_tracks_ignored(self):
        detector = AnomalyDetector(crowd_threshold=2)
        tracks = [
            _make_track(1, 100, 100, confirmed=True),
            _make_track(2, 100, 100, confirmed=False),
            _make_track(3, 100, 100, confirmed=False),
        ]
        anomalies = detector.update(tracks, (480, 640, 3))
        crowd_anomalies = [a for a in anomalies if a["type"] == "crowd"]
        assert len(crowd_anomalies) == 0

    def test_multiple_zones(self):
        """Tracks in different zones should be counted separately."""
        detector = AnomalyDetector(crowd_threshold=2)
        tracks = [
            _make_track(1, 100, 100),    # top-left
            _make_track(2, 500, 100),    # top-right
        ]
        anomalies = detector.update(tracks, (480, 640, 3))
        crowd_anomalies = [a for a in anomalies if a["type"] == "crowd"]
        assert len(crowd_anomalies) == 0  # 1 per zone, below threshold


class TestAnomalyDetectorSeverity:
    def test_high_severity_double_threshold(self):
        detector = AnomalyDetector(crowd_threshold=3)
        # 6 people = 2x threshold → high severity
        tracks = [_make_track(i, 100, 100) for i in range(6)]
        anomalies = detector.update(tracks, (480, 640, 3))
        crowd_anomalies = [a for a in anomalies if a["type"] == "crowd"]
        assert len(crowd_anomalies) >= 1
        assert crowd_anomalies[0]["severity"] == "high"

    def test_medium_severity_at_threshold(self):
        detector = AnomalyDetector(crowd_threshold=3)
        tracks = [_make_track(i, 100, 100) for i in range(4)]
        anomalies = detector.update(tracks, (480, 640, 3))
        crowd_anomalies = [a for a in anomalies if a["type"] == "crowd"]
        assert len(crowd_anomalies) >= 1
        assert crowd_anomalies[0]["severity"] == "medium"

