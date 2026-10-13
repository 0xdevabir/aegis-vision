#!/usr/bin/env python3
"""
Pipeline evaluation script for thesis / defense results.

Measures per-stage timing and throughput on a video file or camera.

Usage:
    python scripts/evaluate_pipeline.py --video data/demo/clips/sample.mp4 --frames 200
    python scripts/evaluate_pipeline.py --frames 100
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from core.app.factory import build_pipeline
from main import _resolve_camera_index
from utils.media import open_capture


def evaluate(source, max_frames: int, base_dir: str) -> dict:
    config_path = os.path.join(base_dir, "config", "config.yaml")
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    pipeline, _, camera_location = build_pipeline(cfg, base_dir)
    cap = open_capture(source)

    timings = []
    start = time.time()
    processed = 0

    for _ in range(max_frames):
        ret, frame = cap.read()
        if not ret:
            break
        t0 = time.perf_counter()
        pipeline.run(frame, camera_id="eval", camera_location=camera_location)
        timings.append((time.perf_counter() - t0) * 1000)
        processed += 1

    cap.release()
    elapsed = time.time() - start
    avg_ms = sum(timings) / max(len(timings), 1)
    fps = processed / max(elapsed, 0.001)

    return {
        "source": str(source),
        "frames_processed": processed,
        "elapsed_seconds": round(elapsed, 2),
        "avg_frame_ms": round(avg_ms, 2),
        "throughput_fps": round(fps, 2),
        "pipeline_stats": pipeline.get_stats(),
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate surveillance pipeline performance")
    parser.add_argument("--video", type=str, default="", help="Video file path")
    parser.add_argument("--frames", type=int, default=100, help="Max frames to process")
    parser.add_argument("--output", type=str, default="", help="Save JSON report to file")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config", "config.yaml")
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    source = args.video if args.video else _resolve_camera_index(cfg)
    print(f"Evaluating {source} for up to {args.frames} frames...")

    try:
        report = evaluate(source, args.frames, base_dir)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        print("Place a demo video at data/demo/clips/sample.mp4 or pass --video")
        sys.exit(1)
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print(json.dumps(report, indent=2))
    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Report saved to {args.output}")


if __name__ == "__main__":
    main()

