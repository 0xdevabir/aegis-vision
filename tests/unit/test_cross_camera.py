"""Cross-camera tracking: a red-alert subject is recognised again by appearance on another camera."""

import numpy as np

from core.tracking.cross_camera import CrossCameraTracker

BOX = (100, 100, 200, 400)
RED, BLUE = np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])


def _frame(v):
    """A frame whose 'appearance' is simply the vector painted into its first pixel."""
    f = np.zeros((480, 640, 3), np.float32)
    f[100, 100] = v
    return f


def _tracker(**kw):
    return CrossCameraTracker(embed_fn=lambda crop: crop[0, 0].astype(float), threshold=0.6, enabled=True, **kw)


def _subject(tid=1):
    return [(tid, BOX, "name:x", "x", "CRIMINAL_DETECTED", "x")]


def test_subject_is_followed_onto_another_camera_after_two_matching_looks():
    t = _tracker()
    assert t.step("gate", "Gate", 100.0, _frame(RED), _subject(), []) == {}
    assert t.step("hall", "Hall", 110.0, _frame(RED), [], [(7, BOX)]) == {}        # one look is not enough
    found = t.step("hall", "Hall", 111.0, _frame(RED), [], [(7, BOX)])
    assert found[7].label == "x" and found[7].origin_location == "Gate"
    assert [c for c, _, _ in found[7].trail] == ["gate", "hall"]


def test_someone_who_looks_different_is_not_followed():
    t = _tracker()
    t.step("gate", "Gate", 100.0, _frame(RED), _subject(), [])
    for now in (110.0, 111.0, 112.0):
        assert t.step("hall", "Hall", now, _frame(BLUE), [], [(7, BOX)]) == {}


def test_another_person_beside_the_live_subject_is_not_the_subject():
    t = _tracker()
    for now in (100.0, 101.0, 102.0):
        assert t.step("gate", "Gate", now, _frame(RED), _subject(), [(2, BOX)]) == {}


def test_follow_is_dropped_when_the_track_stops_matching():
    t = _tracker()
    t.step("gate", "Gate", 100.0, _frame(RED), _subject(), [])
    t.step("hall", "Hall", 110.0, _frame(RED), [], [(7, BOX)])
    assert 7 in t.step("hall", "Hall", 111.0, _frame(RED), [], [(7, BOX)])
    t.step("hall", "Hall", 114.5, _frame(BLUE), [], [(7, BOX)])
    assert t.step("hall", "Hall", 118.0, _frame(BLUE), [], [(7, BOX)]) == {}


def test_subject_is_forgotten_after_the_ttl():
    t = _tracker(ttl=60)
    t.step("gate", "Gate", 100.0, _frame(RED), _subject(), [])
    t.step("hall", "Hall", 200.0, _frame(RED), [], [(7, BOX)])
    assert t.targets == {}


def test_disabled_or_without_a_model_nothing_is_followed():
    off = CrossCameraTracker(embed_fn=lambda crop: RED, enabled=False)
    assert off.step("gate", "Gate", 100.0, _frame(RED), _subject(), [(2, BOX)]) == {}
    no_model = CrossCameraTracker(embed_fn=lambda crop: None, enabled=True)
    no_model.step("gate", "Gate", 100.0, _frame(RED), _subject(), [])
    assert no_model.step("hall", "Hall", 101.0, _frame(RED), [], [(7, BOX)]) == {}
