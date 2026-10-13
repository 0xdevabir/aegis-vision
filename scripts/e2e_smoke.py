"""End-to-end smoke run of the REAL pipeline (factory, real models) on a video file.

Uses a throwaway SQLite DB and disables alert publishing, so it touches nothing.
Prints per-stage timings and detection counts; exits non-zero if no frame processed.

    python scripts/e2e_smoke.py data/recordings/laptop/continuous/20260802/152747_laptop.mp4 --frames 60
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_tmp = tempfile.mkdtemp(prefix="aegis_e2e_")
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_tmp}/e2e.db",
    "USE_SQLITE": "false",          # otherwise .env's USE_SQLITE=true ignores DATABASE_URL
    "AUTO_ALERTS_ENABLED": "false",
    "PIPELINE_EVENTS_ENABLED": "false",
    "DVR_ENABLED": "false",
})

import cv2  # noqa: E402

from backend.db.database import init_db  # noqa: E402
from core.app.factory import build_pipeline  # noqa: E402
from utils.config import load_yaml  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--frames", type=int, default=60)
    a = ap.parse_args()

    init_db()
    cfg = load_yaml(str(ROOT / "config" / "config.yaml"))
    pipeline, _, _ = build_pipeline(cfg, str(ROOT), camera_location="e2e")

    cap = cv2.VideoCapture(a.video)
    n = people = poses = 0
    while n < a.frames:
        ok, frame = cap.read()
        if not ok:
            break
        ctx = pipeline.run(frame, camera_id="e2e", camera_location="e2e")
        n += 1
        people += len([t for t in ctx.tracks if t.is_confirmed()])
        poses += len(getattr(pipeline.stages[3], "_last_poses", {}))
    cap.release()

    stats = pipeline.get_stats()
    print(f"frames={n} confirmed_track_frames={people} pose_matches={poses}")
    for s in stats["stages"]:
        print(f"  {s['name']:<12} avg {s['avg_ms']:>8.1f} ms")
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main())
