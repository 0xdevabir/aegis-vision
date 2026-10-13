"""Compare detector models on YOUR footage before choosing one.

Latency/FPS on a video, and (optionally) precision/recall/mAP on a labelled
YOLO-format dataset via ultralytics' validator.

    python scripts/benchmark_detectors.py --video data/demo/clips/sample.mp4 \
        --models models/yolov8n.pt models/yolov8s.pt --device auto --frames 200
    python scripts/benchmark_detectors.py --models models/weapon_yolo.pt \
        --data datasets/weapons/data.yaml
"""

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402
from ultralytics import YOLO  # noqa: E402

from core.detectors.device import resolve_device  # noqa: E402


def bench(model_path: str, video: str, device: str, frames: int, imgsz: int):
    model = YOLO(model_path)
    cap = cv2.VideoCapture(video)
    times = []
    for i in range(frames + 3):
        ok, frame = cap.read()
        if not ok:
            break
        t0 = time.perf_counter()
        model(frame, imgsz=imgsz, device=device, verbose=False)
        if i >= 3:                       # skip warm-up
            times.append((time.perf_counter() - t0) * 1000)
    cap.release()
    if not times:
        return None
    times.sort()
    return {
        "model": model_path, "device": device, "frames": len(times),
        "mean_ms": round(statistics.mean(times), 1),
        "p95_ms": round(times[int(len(times) * 0.95) - 1], 1),
        "fps": round(1000 / statistics.mean(times), 1),
    }


def evaluate(model_path: str, data: str, device: str, imgsz: int):
    m = YOLO(model_path).val(data=data, device=device, imgsz=imgsz, verbose=False)
    return {
        "model": model_path, "precision": round(float(m.box.mp), 3),
        "recall": round(float(m.box.mr), 3), "mAP50": round(float(m.box.map50), 3),
        "mAP50-95": round(float(m.box.map), 3),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--video")
    ap.add_argument("--data", help="YOLO dataset yaml with labelled val split")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--frames", type=int, default=100)
    ap.add_argument("--imgsz", type=int, default=640)
    a = ap.parse_args()
    device = resolve_device(a.device)
    for mp in a.models:
        if a.video:
            print(bench(mp, a.video, device, a.frames, a.imgsz))
        if a.data:
            print(evaluate(mp, a.data, device, a.imgsz))


if __name__ == "__main__":
    main()
