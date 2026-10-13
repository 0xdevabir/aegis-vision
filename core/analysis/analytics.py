import numpy as np
from collections import defaultdict, deque
from datetime import datetime


class Analytics:
    def __init__(self):
        self.heatmap = None
        self.dwell_data = defaultdict(list)
        self.movement_paths = defaultdict(deque)
        self._frame_w = 640

    def update_heatmap(self, tracks, frame_shape):
        h, w = frame_shape[:2]
        self._frame_w = w
        if self.heatmap is None or self.heatmap.shape != (h, w):
            # First frame, or the stream changed resolution (reconnect, different source).
            self.heatmap = np.zeros((h, w), dtype=np.float32)
        for track in tracks:
            if not track.is_confirmed():
                continue
            x1, y1, x2, y2 = map(int, track.to_ltrb())
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            if 0 <= cx < w and 0 <= cy < h:
                self.heatmap[cy, cx] += 1.0
        self.heatmap = np.clip(self.heatmap, 0, 255)

    def get_heatmap_normalized(self):
        if self.heatmap is None:
            return None
        max_val = self.heatmap.max()
        if max_val > 0:
            return (self.heatmap / max_val * 255).astype(np.uint8)
        return self.heatmap.astype(np.uint8)

    def record_dwell(self, track_id: int, zone: str, duration: float):
        self.dwell_data[zone].append({
            "track_id": track_id,
            "duration": duration,
            "timestamp": datetime.now().isoformat(),
        })

    def record_movement(self, track_id: int, x: float, y: float):
        path = self.movement_paths[track_id]
        path.append((x, y, datetime.now().timestamp()))
        while len(path) > 600:   # bound memory per track
            path.popleft()

    def get_dwell_stats(self):
        stats = {}
        for zone, records in self.dwell_data.items():
            durations = [r["duration"] for r in records]
            stats[zone] = {
                "count": len(records),
                "avg_duration": np.mean(durations) if durations else 0,
                "max_duration": max(durations) if durations else 0,
            }
        return stats

    def get_traffic_flow(self, interval_seconds: int = 60):
        cutoff = datetime.now().timestamp() - interval_seconds
        flow = defaultdict(int)
        for tid, path in self.movement_paths.items():
            for x, y, ts in path:
                if ts >= cutoff:
                    zone = "left" if x < self._frame_w / 2 else "right"
                    flow[zone] += 1
        return dict(flow)
