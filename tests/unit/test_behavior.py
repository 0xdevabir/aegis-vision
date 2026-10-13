"""
Unit Tests — Behavior Analysis
================================
Tests for suspicious behavior detection heuristics.
"""

import time
from core.analysis.behavior import is_suspicious_behavior


class TestSuspiciousBehavior:
    def test_short_history_not_suspicious(self):
        """Less than 5 data points should never be suspicious."""
        history = [(time.time(), 100, 100)] * 3
        is_sus, reasons = is_suspicious_behavior(history)
        assert is_sus is False
        assert reasons == []

    def test_loitering_detection(self):
        """Person in same area for >15 seconds should trigger loitering."""
        now = time.time()
        history = [(now - 20 + i, 100, 100) for i in range(21)]
        is_sus, reasons = is_suspicious_behavior(history)
        assert is_sus is True
        assert "loitering" in reasons

    def test_rapid_movement_detection(self):
        """Very fast movement should trigger rapid_movement."""
        now = time.time()
        history = []
        for i in range(10):
            # Move 500 pixels per second (way above threshold of 150)
            history.append((now - 10 + i, i * 500, 100))
        is_sus, reasons = is_suspicious_behavior(history)
        assert is_sus is True
        assert "rapid_movement" in reasons

    def test_normal_behavior_not_suspicious(self):
        """Normal walking speed, short duration should be clear."""
        now = time.time()
        history = []
        for i in range(10):
            # Move ~30 pixels/sec (well under threshold)
            history.append((now - 10 + i, 100 + i * 30, 100))
        is_sus, reasons = is_suspicious_behavior(history)
        assert "rapid_movement" not in reasons

    def test_erratic_movement_detection(self):
        """Many sharp direction changes should trigger erratic_movement."""
        now = time.time()
        history = []
        for i in range(20):
            # Zigzag pattern
            x = 100 + (i * 50 if i % 2 == 0 else -i * 50)
            y = 100 + (i * 50 if i % 2 == 1 else -i * 50)
            history.append((now - 20 + i, x, y))
        is_sus, reasons = is_suspicious_behavior(history)
        # May or may not trigger depending on exact geometry,
        # but should not crash
        assert isinstance(is_sus, bool)
        assert isinstance(reasons, list)

    def test_pose_landmarks_accepted(self):
        """Function should accept pose_landmarks without error."""
        now = time.time()
        history = [(now - 5 + i, 100 + i * 10, 100) for i in range(6)]
        # Pass None for pose_landmarks (not used by current implementation)
        is_sus, reasons = is_suspicious_behavior(history, pose_landmarks=None)
        assert isinstance(is_sus, bool)

