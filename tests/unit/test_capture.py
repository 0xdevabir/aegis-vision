"""Red-alert capture: zoom crop, per-subject throttle, clothing colour description."""

from unittest.mock import patch

import numpy as np

from utils.alerts.capture import AlertCapturer, zoom_crop
from utils.face_attributes import clothing_colours


def _frame():
    return np.zeros((720, 1280, 3), np.uint8)


class TestZoomCrop:
    def test_small_subject_is_enlarged(self):
        image, box = zoom_crop(_frame(), (600, 300, 660, 420), min_side=720, max_zoom=4.0)
        assert box == (588, 276, 672, 444)                  # 20% margin on each side
        assert image.shape[0] == 168 * 4                    # zoom capped at 4x

    def test_box_is_clamped_to_frame(self):
        _, box = zoom_crop(_frame(), (-50, -50, 100, 200))
        assert box[0] == 0 and box[1] == 0

    def test_empty_box(self):
        assert zoom_crop(_frame(), (10, 10, 12, 12)) is None


class TestAlertCapturer:
    def _capture(self, cap, now, key="track_1", camera_id="cam_1"):
        return cap.capture(key, now, _frame(), (100, 100, 300, 600),
                           camera_id=camera_id, alert_type="CRIMINAL_DETECTED", track_id=1)

    def test_one_capture_per_interval(self):
        cap = AlertCapturer(interval=5.0, enabled=True)
        with patch("utils.alerts.capture.publish_capture") as publish:
            assert self._capture(cap, 100.0)
            assert not self._capture(cap, 102.0)
            assert self._capture(cap, 105.0)
            assert publish.call_count == 2

    def test_subjects_and_cameras_are_independent(self):
        cap = AlertCapturer(interval=5.0, enabled=True)
        with patch("utils.alerts.capture.publish_capture") as publish:
            self._capture(cap, 100.0)
            self._capture(cap, 100.5, key="track_2")
            self._capture(cap, 100.6, camera_id="cam_2")
            assert publish.call_count == 3

    def test_payload_carries_position_and_jpeg(self):
        cap = AlertCapturer(interval=5.0, enabled=True)
        with patch("utils.alerts.capture.publish_capture") as publish:
            self._capture(cap, 100.0)
            camera_id, jpeg, fields = publish.call_args[0]
            assert camera_id == "cam_1"
            assert jpeg[:2] == b"\xff\xd8"
            x, y, w, h = map(float, fields["bbox"].split(","))
            assert 0 <= x < x + w <= 1 and 0 <= y < y + h <= 1
            assert fields["alert_type"] == "CRIMINAL_DETECTED"

    def test_disabled(self):
        cap = AlertCapturer(interval=5.0, enabled=False)
        with patch("utils.alerts.capture.publish_capture") as publish:
            assert not self._capture(cap, 100.0)
            publish.assert_not_called()


class TestClothingColours:
    def test_upper_and_lower(self):
        person = np.zeros((400, 160, 3), np.uint8)
        person[60:200] = (200, 40, 30)      # blue top (BGR)
        person[200:400] = (20, 20, 20)      # black trousers
        out = clothing_colours(person)
        assert out["upper_colour"]["name"] == "blue"
        assert out["lower_colour"]["name"] == "black"

    def test_not_a_standing_person(self):
        assert clothing_colours(np.zeros((100, 300, 3), np.uint8)) == {}
