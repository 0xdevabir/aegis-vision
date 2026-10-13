"""Clean overlay for the dashboard video stream: people marked, nothing else.

The full HUD (core/visualization/hud.py) is built for a local OpenCV window: face panels, radar,
threat bar, stats box, banners. On the dashboard those duplicated the tile's own status chips and
covered a quarter of the picture. This draws only what the operator needs on the video itself:

* a box around every person the detector sees right now (green, orange if suspicious, red if on the
  watchlist or armed), with corner accents so it reads at a glance;
* a small label chip: "Person" for everyone, the watchlist name for a match.

Boxes are eased toward each new AI result every rendered frame. AI results arrive at 5-10 Hz while
the video runs at the camera's rate, so un-eased boxes visibly jump between results.
"""

from __future__ import annotations

import cv2

GREEN = (80, 200, 90)        # BGR
ORANGE = (0, 150, 255)
RED = (50, 50, 235)
WHITE = (255, 255, 255)
EASE = 0.45                  # share of the gap to the newest box covered per rendered frame
DROP_AFTER = 1.0             # seconds a person may go unseen before their box is removed


class StreamOverlay:
    """One per camera: keeps each person's displayed box between AI results."""

    def __init__(self):
        self._shown: dict = {}        # track_id -> [x1, y1, x2, y2] (floats, source-frame pixels)
        self._seen: dict = {}         # track_id -> monotonic time of the last AI sighting

    def _update(self, ctx, now: float) -> list:
        """(track_id, box) for people to draw this frame, boxes eased toward the latest AI result."""
        for t in ctx.tracks:
            # Only people detected in the latest AI frame: a lost track coasts on a predicted box
            # that drifts onto background, and tentative tracks flicker.
            if not t.is_confirmed() or getattr(t, "time_since_update", 0) != 0:
                continue
            target = [float(v) for v in t.to_ltrb()]
            cur = self._shown.get(t.track_id)
            if cur is None:
                self._shown[t.track_id] = target
            else:
                for i in range(4):
                    cur[i] += (target[i] - cur[i]) * EASE
            self._seen[t.track_id] = now
        for tid in [k for k, ts in self._seen.items() if now - ts > DROP_AFTER]:
            self._seen.pop(tid, None)
            self._shown.pop(tid, None)
        # Draw only people from the newest result (the AI result is stamped each time it changes).
        live = {t.track_id for t in ctx.tracks
                if t.is_confirmed() and getattr(t, "time_since_update", 0) == 0}
        return [(tid, box) for tid, box in self._shown.items() if tid in live]

    def render(self, img, ctx, scale: float, now: float):
        """Draw onto `img` (already resized by `scale` from the source frame) and return it."""
        if ctx is None:
            return img
        h, w = img.shape[:2]
        # Sizes follow the picture width so a 1280px stream and a 640px one look alike.
        thick = max(2, round(w / 640))
        font = 0.45 * max(1.0, w / 960)
        for tid, (x1, y1, x2, y2) in self._update(ctx, now):
            x1, y1, x2, y2 = (int(max(0, min(v * scale, lim))) for v, lim in
                              ((x1, w - 1), (y1, h - 1), (x2, w - 1), (y2, h - 1)))
            if x2 - x1 < 4 or y2 - y1 < 4:
                continue
            name = ctx.identities.get(tid, "Unknown")
            if tid in ctx.criminal_ids or tid in ctx.confirmed_weapons:
                color = RED
                label = f"WATCHLIST  {name}" if tid in ctx.criminal_ids else "ARMED"
            elif tid in ctx.suspicious_tracks:
                color, label = ORANGE, "Person  suspicious"
            else:
                color, label = GREEN, "Person"
            self._box(img, x1, y1, x2, y2, color, thick)
            self._label(img, label, x1, y1, color, font, thick)
        return img

    @staticmethod
    def _box(img, x1, y1, x2, y2, color, thick):
        """Thin full outline plus bold corners."""
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 1)
        n = max(10, min(x2 - x1, y2 - y1) // 5)
        # Thick anti-aliased lines cost ~10x plain ones on a 720p frame; at this stroke width the
        # difference is invisible, and this runs every frame for every person on every camera.
        for (cx, cy, dx, dy) in ((x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)):
            cv2.line(img, (cx, cy), (cx + dx * n, cy), color, thick + 1)
            cv2.line(img, (cx, cy), (cx, cy + dy * n), color, thick + 1)

    @staticmethod
    def _label(img, text, x1, y1, color, font, thick):
        (tw, th), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font, 1)
        pad = 4
        top = y1 - th - base - 2 * pad
        if top < 0:                                   # box touches the top edge: put the chip inside
            top = y1 + 1
        x2 = min(x1 + tw + 2 * pad, img.shape[1] - 1)
        cv2.rectangle(img, (x1, top), (x2, top + th + base + 2 * pad), color, -1)
        cv2.putText(img, text, (x1 + pad, top + th + pad), cv2.FONT_HERSHEY_SIMPLEX, font, WHITE, 1, cv2.LINE_AA)
