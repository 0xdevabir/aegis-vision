"""The alert-worthy identity set follows database changes without a pipeline restart."""
import time

from utils import live_names


def test_criminal_names_refresh_in_place(monkeypatch):
    monkeypatch.setattr(live_names, "_CACHE", {})
    db = {"P-1"}
    names = live_names.live_criminal_names({"CFG_ONE"}, lambda: set(db), interval=0.05)
    assert names == {"CFG_ONE", "P-1"}

    db.add("P-NEW")                      # enrolled in the dashboard afterwards
    deadline = time.time() + 2
    while "P-NEW" not in names and time.time() < deadline:
        time.sleep(0.02)
    assert "P-NEW" in names

    db.discard("P-1")                    # cleared / deleted
    deadline = time.time() + 2
    while "P-1" in names and time.time() < deadline:
        time.sleep(0.02)
    assert "P-1" not in names and "CFG_ONE" in names   # config names are permanent


def test_same_set_object_is_shared_between_cameras(monkeypatch):
    monkeypatch.setattr(live_names, "_CACHE", {})
    a = live_names.live_criminal_names({"X"}, lambda: set(), interval=60)
    b = live_names.live_criminal_names({"X"}, lambda: set(), interval=60)
    assert a is b
