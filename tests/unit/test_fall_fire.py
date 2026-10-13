from unittest.mock import MagicMock

from core.analysis.behavior import is_suspicious_behavior
from core.analysis.fall import FallDetector, posture
from core.analysis.pose import assign_poses
from core.analysis.weapon_confirm import WeaponConfirmer


def kp(sx, sy, hx, hy):
    """Shoulders and hips only (left/right identical for simplicity)."""
    pt = lambda x, y: (x, y, 0.9)  # noqa: E731
    return {"left_shoulder": pt(sx - 10, sy), "right_shoulder": pt(sx + 10, sy),
            "left_hip": pt(hx - 10, hy), "right_hip": pt(hx + 10, hy)}


UPRIGHT = (kp(100, 50, 100, 130), (60, 20, 140, 220))      # tall box, vertical torso
LYING = (kp(50, 190, 130, 195), (20, 160, 200, 220))       # wide box, horizontal torso


def test_posture_classification():
    assert posture(*UPRIGHT) == "upright"
    assert posture(*LYING) == "horizontal"
    assert posture({}, (0, 0, 10, 10)) is None


def test_fall_requires_prior_upright_and_duration():
    d = FallDetector(upright_memory=4, lie_seconds=2)
    assert not d.update(1, *UPRIGHT, now=0)
    assert not d.update(1, *LYING, now=1)               # just went down
    assert not d.update(1, *LYING, now=2.5)             # < 2 s lying
    assert d.update(1, *LYING, now=3.2)                 # sustained → alert
    assert not d.update(1, *LYING, now=4)               # once per episode


def test_person_already_lying_never_alerts():
    d = FallDetector()
    for t in range(10):
        assert not d.update(7, *LYING, now=float(t))


def test_stand_up_resets_episode():
    d = FallDetector(lie_seconds=1)
    d.update(1, *UPRIGHT, now=0)
    d.update(1, *LYING, now=1)
    assert d.update(1, *LYING, now=2.1)
    d.update(1, *UPRIGHT, now=3)
    d.update(1, *LYING, now=4)
    assert d.update(1, *LYING, now=5.1)


def test_assign_poses_by_overlap():
    t = MagicMock(track_id=3)
    t.is_confirmed.return_value = True
    t.to_ltrb.return_value = (0, 0, 100, 200)
    poses = [{"bbox": (10, 10, 90, 190), "kpts": {}}, {"bbox": (400, 0, 480, 200), "kpts": {}}]
    assert list(assign_poses(poses, [t])) == [3]
    assert assign_poses(poses[1:], [t]) == {}


def test_raised_arms_uses_dict_keypoints_and_scales():
    pose = {"left_shoulder": (90, 100, 1), "right_shoulder": (110, 100, 1),
            "left_hip": (90, 200, 1), "right_hip": (110, 200, 1),
            "left_wrist": (80, 40, 1)}                   # 60 px above shoulders, torso 100 px
    history = [(i * 0.1, 100, 100) for i in range(6)]
    assert "raised_arms" in is_suspicious_behavior(history, pose)[1]
    pose["left_wrist"] = (80, 90, 1)                     # only 10 px above → not raised
    assert "raised_arms" not in is_suspicious_behavior(history, pose)[1]


def test_fire_needs_5_of_8_frames():
    c = WeaponConfirmer(window=8, min_hits=5)
    hit = {"fire": {"score": 0.7}}
    out = [c.update(hit if i % 2 == 0 else {}) for i in range(8)]   # flicker: 4 of 8
    assert all(o == set() for o in out)
    c = WeaponConfirmer(window=8, min_hits=5)
    res = [c.update(hit) for _ in range(5)]
    assert res[:4] == [set()] * 4 and res[4] == {"fire"}
