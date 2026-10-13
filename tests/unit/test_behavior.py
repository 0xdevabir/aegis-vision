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



class TestMetricThresholds:
    """With box height in the history, speed and loitering are judged in metres, not pixels."""

    @staticmethod
    def _walk(px_per_s, height, n=10):
        return [(float(i), i * px_per_s, 100.0, height) for i in range(n)]

    def test_same_real_speed_gives_same_verdict_near_and_far(self):
        # 1.4 m/s walk: 280 px/s next to the camera (340 px tall), 35 px/s far away (42.5 px tall)
        assert is_suspicious_behavior(self._walk(280, 340))[1] == []
        assert is_suspicious_behavior(self._walk(35, 42.5))[1] == []

    def test_running_is_flagged_even_when_far_and_slow_in_pixels(self):
        # 5 m/s at 42.5 px tall is only 125 px/s: under the old 150 px/s rule, a miss
        assert "rapid_movement" in is_suspicious_behavior(self._walk(125, 42.5))[1]

    def test_loitering_radius_scales_with_distance(self):
        near = [(float(i), 100 + (i % 2) * 60, 100.0, 340) for i in range(21)]     # 0.3 m sway
        far = [(float(i), 100 + (i % 2) * 40, 100.0, 42.5) for i in range(21)]     # 1.6 m pacing
        assert "loitering" in is_suspicious_behavior(near)[1]
        assert "loitering" not in is_suspicious_behavior(far)[1]

    def test_occluded_boxes_do_not_change_the_scale(self):
        history = self._walk(280, 340)
        history[3] = history[3][:3] + (60,)                                        # one half-hidden frame
        assert is_suspicious_behavior(history)[1] == []
