from core.analysis.weapon_confirm import UNASSIGNED, WeaponConfirmer, associate


class T:
    def __init__(self, tid, box):
        self.track_id, self._b = tid, box

    def is_confirmed(self):
        return True

    def to_ltrb(self):
        return self._b


def det(box, score=0.6):
    return {"bbox": box, "score": score, "class_id": 0}


def test_weapon_assigned_only_to_overlapping_person():
    tracks = [T(1, (0, 0, 100, 200)), T(2, (300, 0, 400, 200))]
    got = associate([det((10, 80, 40, 110))], tracks)
    assert list(got) == [1]


def test_unmatched_weapon_goes_to_unassigned():
    got = associate([det((500, 500, 520, 520))], [T(1, (0, 0, 100, 200))])
    assert list(got) == [UNASSIGNED]


def test_single_frame_never_confirms():
    c = WeaponConfirmer(window=5, min_hits=3)
    assert c.update({1: det((0, 0, 1, 1))}) == set()


def test_confirms_after_min_hits_and_decays():
    c = WeaponConfirmer(window=5, min_hits=3)
    hit = {1: det((0, 0, 1, 1))}
    assert c.update(hit) == set()
    assert c.update({}) == set()
    assert c.update(hit) == set()
    assert c.update(hit) == {1}
    for _ in range(5):
        c.update({})
    assert c.update(hit) == set()
