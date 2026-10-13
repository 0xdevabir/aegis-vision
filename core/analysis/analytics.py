import time
from collections import defaultdict, deque

import numpy as np

GRID_H, GRID_W = 27, 48          # 16:9 occupancy grid, independent of stream resolution
# 3x3 splat so one person warms a patch of floor instead of a single cell
_SPLAT = np.array([[0.25, 0.5, 0.25], [0.5, 1.0, 0.5], [0.25, 0.5, 0.25]], dtype=np.float32)


class Analytics:
    """Per-camera occupancy heatmap, zone dwell and line-crossing flow."""

    def __init__(self, flow_window: float = 60.0, max_dwell_records: int = 500):
        self.heatmap = np.zeros((GRID_H + 2, GRID_W + 2), dtype=np.float32)   # 1-cell border for the splat
        self.flow_window = flow_window
        self.dwell_data = defaultdict(lambda: deque(maxlen=max_dwell_records))
        self._crossings = deque()            # (ts, line, direction)
        self._seen = {}                      # track id → last seen ts

    def update_heatmap(self, tracks, frame_shape, now: float = None):
        """Accumulate each confirmed track's foot point (where the person stands, not their chest)."""
        h, w = frame_shape[:2]
        now = time.time() if now is None else now
        for track in tracks:
            if not track.is_confirmed():
                continue
            x1, _, x2, y2 = track.to_ltrb()
            self._seen[track.track_id] = now
            gx = int((x1 + x2) / 2 / w * GRID_W)
            gy = int(y2 / h * GRID_H)
            if 0 <= gx < GRID_W and 0 <= gy < GRID_H:
                self.heatmap[gy:gy + 3, gx:gx + 3] += _SPLAT
        for tid in [t for t, ts in self._seen.items() if now - ts > self.flow_window]:
            del self._seen[tid]

    def get_heatmap_grid(self):
        """GRID_H x GRID_W rows of 0-100 intensity (JSON-ready for the dashboard)."""
        grid = self.heatmap[1:-1, 1:-1]
        peak = float(grid.max())
        if peak <= 0:
            return np.zeros_like(grid, dtype=int).tolist()
        return np.rint(grid / peak * 100).astype(int).tolist()

    def record_dwell(self, track_id, zone: str, duration: float):
        self.dwell_data[zone].append({"track_id": track_id, "duration": duration, "timestamp": time.time()})

    def record_crossing(self, line: str, direction: int, now: float = None):
        self._crossings.append((time.time() if now is None else now, line, direction))

    def get_dwell_stats(self):
        stats = {}
        for zone, records in self.dwell_data.items():
            durations = [r["duration"] for r in records]
            stats[zone] = {
                "count": len(records),
                "avg_duration": float(np.mean(durations)) if durations else 0,
                "max_duration": max(durations) if durations else 0,
            }
        return stats

    def get_traffic_flow(self, now: float = None):
        """People seen and line crossings per direction over the last `flow_window` seconds."""
        now = time.time() if now is None else now
        cutoff = now - self.flow_window
        while self._crossings and self._crossings[0][0] < cutoff:
            self._crossings.popleft()
        lines = defaultdict(lambda: {"in": 0, "out": 0})
        for _, line, direction in self._crossings:
            lines[line]["in" if direction > 0 else "out"] += 1
        return {
            "window_seconds": self.flow_window,
            "people": sum(1 for ts in self._seen.values() if ts >= cutoff),
            "lines": dict(lines),
        }
