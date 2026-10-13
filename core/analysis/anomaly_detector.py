"""Zone-based anomaly detection: crowd, dwell, restricted-zone intrusion, line crossing.

Zones are normalized polygons (see zones.py); with none configured, the frame is
split into four quadrants (legacy behaviour). Dwell and intrusion events are emitted
once per track entry, and per-track state is dropped when a track leaves a zone or
disappears.
"""

import time
from collections import defaultdict
from typing import List, Optional

from core.analysis.zones import (
    QUADRANT_ZONES, Line, Zone, crossed, parse_lines, parse_zones,
)


class AnomalyDetector:
    def __init__(self, crowd_threshold: int = 5, dwell_seconds: int = 300,
                 zones: Optional[list] = None, lines: Optional[list] = None):
        self.crowd_threshold = crowd_threshold
        self.dwell_seconds = dwell_seconds
        self.zone_counts = defaultdict(int)
        self.set_geometry(zones, lines)

    def set_geometry(self, zones: Optional[list], lines: Optional[list]) -> None:
        """Replace zones/lines (also used for live edits from the dashboard).

        Per-track state is reset: dwell timers and 'already reported' flags belong to
        the old zones and would be meaningless — or suppress alerts — under new ones.
        """
        self.zones: List[Zone] = parse_zones(zones) or parse_zones(QUADRANT_ZONES)
        self.lines: List[Line] = parse_lines(lines)
        self.zone_counts.clear()
        self._entered = {z.name: {} for z in self.zones}      # zone → {tid: entry_ts}
        self._reported = {z.name: set() for z in self.zones}  # (dwell/intrusion) once per entry
        self._last_pos = {}                                   # tid → (nx, ny)

    def update(self, tracks, frame_shape, now: Optional[float] = None):
        h, w = frame_shape[:2]
        now = time.time() if now is None else now
        anomalies = []

        present = {}
        for t in tracks:
            if not t.is_confirmed():
                continue
            x1, y1, x2, y2 = map(int, t.to_ltrb())
            # Foot point (bottom-centre) is the right ground reference for zones.
            present[t.track_id] = (((x1 + x2) / 2) / w, y2 / h)

        for zone in self.zones:
            inside = {tid for tid, (nx, ny) in present.items() if zone.contains(nx, ny)}
            self.zone_counts[zone.name] = len(inside)

            entered = self._entered[zone.name]
            for tid in list(entered):
                if tid not in inside:               # left the zone or lost → reset
                    del entered[tid]
                    self._reported[zone.name].discard(tid)
            for tid in inside:
                entered.setdefault(tid, now)

            if len(inside) >= self.crowd_threshold:
                anomalies.append({
                    "type": "crowd", "zone": zone.name, "count": len(inside),
                    "severity": "high" if len(inside) >= self.crowd_threshold * 2 else "medium",
                    "message": f"Crowd of {len(inside)} in {zone.name}",
                })

            for tid in inside:
                key = tid
                if key in self._reported[zone.name]:
                    continue
                if zone.type == "restricted":
                    self._reported[zone.name].add(key)
                    anomalies.append({
                        "type": "intrusion", "zone": zone.name, "track_id": tid,
                        "severity": "high",
                        "message": f"Person entered restricted zone {zone.name}",
                    })
                elif now - entered[tid] > self.dwell_seconds:
                    self._reported[zone.name].add(key)
                    anomalies.append({
                        "type": "dwell", "zone": zone.name, "track_id": tid,
                        "duration_seconds": int(now - entered[tid]), "severity": "medium",
                        "message": f"Dwell {int(now - entered[tid])}s in {zone.name}",
                    })

        for tid, pos in present.items():
            prev = self._last_pos.get(tid)
            if prev:
                for ln in self.lines:
                    d = crossed(prev, pos, ln.p1, ln.p2)
                    if d:
                        anomalies.append({
                            "type": "line_cross", "zone": ln.name, "track_id": tid,
                            "direction": d, "severity": "info",
                            "message": f"Line {ln.name} crossed (dir {d:+d})",
                        })
        self._last_pos = present
        return anomalies
