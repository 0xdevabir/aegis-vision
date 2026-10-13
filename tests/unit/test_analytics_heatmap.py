"""Occupancy heatmap, line-crossing flow and dwell stats."""
from types import SimpleNamespace

from core.analysis.analytics import GRID_H, GRID_W, Analytics


def _track(x, y, tid="1"):
    return SimpleNamespace(track_id=tid, is_confirmed=lambda: True,
                           to_ltrb=lambda: (x - 5, y - 50, x + 5, y))      # feet at (x, y)


def _peak(grid):
    return max((v, r, c) for r, row in enumerate(grid) for c, v in enumerate(row))


def test_heatmap_uses_foot_point_and_survives_resolution_change():
    a = Analytics()
    a.update_heatmap([_track(320, 240)], (480, 640, 3))                    # centre of a small frame
    a.update_heatmap([_track(640, 360)], (720, 1280, 3))                   # same spot, bigger frame
    grid = a.get_heatmap_grid()
    assert (len(grid), len(grid[0])) == (GRID_H, GRID_W)
    assert _peak(grid) == (100, GRID_H // 2, GRID_W // 2)


def test_heatmap_spreads_to_neighbours_and_ignores_out_of_frame():
    a = Analytics()
    a.update_heatmap([_track(320, 240), _track(5000, 5000, "2")], (480, 640, 3))
    grid = a.get_heatmap_grid()
    r, c = GRID_H // 2, GRID_W // 2
    assert 0 < grid[r][c + 1] < grid[r][c]
    assert sum(map(sum, grid)) == 100 + 4 * 50 + 4 * 25


def test_empty_heatmap_is_all_zero():
    assert _peak(Analytics().get_heatmap_grid())[0] == 0


def test_traffic_flow_counts_crossings_per_direction_within_window():
    a = Analytics(flow_window=60)
    a.record_crossing("gate", 1, now=10)                                   # too old
    a.record_crossing("gate", 1, now=100)
    a.record_crossing("gate", 1, now=110)
    a.record_crossing("gate", -1, now=120)
    flow = a.get_traffic_flow(now=130)
    assert flow["lines"] == {"gate": {"in": 2, "out": 1}}


def test_traffic_flow_counts_distinct_people_and_forgets_old_ones():
    a = Analytics(flow_window=60)
    a.update_heatmap([_track(10, 100, "a")], (480, 640, 3), now=0)
    a.update_heatmap([_track(10, 100, "b"), _track(20, 100, "b")], (480, 640, 3), now=100)
    assert a.get_traffic_flow(now=100)["people"] == 1
    assert "a" not in a._seen                                               # pruned, no unbounded growth


def test_dwell_stats():
    a = Analytics()
    a.record_dwell("1", "lobby", 300)
    a.record_dwell("2", "lobby", 500)
    assert a.get_dwell_stats() == {"lobby": {"count": 2, "avg_duration": 400.0, "max_duration": 500}}
