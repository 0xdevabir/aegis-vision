"""Dashboard stream overlay: people only, smoothed boxes, no clutter."""
import types

import numpy as np

from core.visualization.stream_overlay import StreamOverlay


class FakeTrack:
    def __init__(self, tid, box, confirmed=True, since=0):
        self.track_id, self._box, self._c, self.time_since_update = tid, box, confirmed, since

    def is_confirmed(self):
        return self._c

    def to_ltrb(self):
        return self._box


def _ctx(tracks, criminals=(), names=None):
    return types.SimpleNamespace(
        tracks=tracks, identities=names or {}, criminal_ids=set(criminals),
        confirmed_weapons=set(), suspicious_tracks=set())


def _blank():
    return np.zeros((360, 640, 3), np.uint8)


def test_nothing_is_drawn_without_people_or_result():
    ov = StreamOverlay()
    assert not StreamOverlay().render(_blank(), None, 1.0, 0.0).any()
    assert not ov.render(_blank(), _ctx([]), 1.0, 0.0).any()


def test_each_confirmed_live_person_is_marked_and_nothing_else():
    img = StreamOverlay().render(_blank(), _ctx([FakeTrack(1, (100, 100, 200, 300))]), 1.0, 0.0)
    ys, xs = np.nonzero(img.any(axis=2))
    assert xs.min() >= 95 and xs.max() <= 205                  # stays on the person's box (+ stroke)
    assert ys.min() >= 70 and ys.max() <= 305                  # (label chip sits just above it)


def test_stale_and_tentative_tracks_are_not_drawn():
    ctx = _ctx([FakeTrack(1, (10, 10, 100, 200), since=3), FakeTrack(2, (200, 10, 300, 200), confirmed=False)])
    assert not StreamOverlay().render(_blank(), ctx, 1.0, 0.0).any()


def test_watchlist_match_is_red_and_others_green():
    ov = StreamOverlay()
    ctx = _ctx([FakeTrack(1, (20, 100, 120, 300)), FakeTrack(2, (300, 100, 400, 300))],
               criminals=[2], names={2: "P-1"})
    img = ov.render(_blank(), ctx, 1.0, 0.0)
    green, red = img[200, 20], img[200, 300]                   # a pixel on each left edge
    assert green[1] > green[2] and red[2] > red[1]             # BGR: green dominant vs red dominant


def test_box_eases_toward_new_position_instead_of_jumping():
    ov = StreamOverlay()
    ov.render(_blank(), _ctx([FakeTrack(1, (100, 100, 200, 300))]), 1.0, 0.0)
    ov.render(_blank(), _ctx([FakeTrack(1, (200, 100, 300, 300))]), 1.0, 0.03)
    x1 = ov._shown[1][0]
    assert 100 < x1 < 200


def test_box_is_forgotten_after_the_person_is_gone():
    ov = StreamOverlay()
    ov.render(_blank(), _ctx([FakeTrack(1, (100, 100, 200, 300))]), 1.0, 0.0)
    ov.render(_blank(), _ctx([]), 1.0, 2.0)
    assert ov._shown == {} and ov._seen == {}


def test_boxes_scale_with_the_resized_stream_frame():
    img = StreamOverlay().render(_blank(), _ctx([FakeTrack(1, (200, 200, 400, 600))]), 0.5, 0.0)
    ys, xs = np.nonzero(img.any(axis=2))
    assert xs.min() >= 95 and xs.max() <= 205                  # 200..400 at half size = 100..200
