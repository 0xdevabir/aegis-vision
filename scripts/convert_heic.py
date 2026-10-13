#!/usr/bin/env python3
"""Convert HEIC/HEIF images in data/watchlist/ to valid JPG for face_recognition."""

import subprocess
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from paths import WATCHLIST_DIR

KNOWN_DIR = WATCHLIST_DIR
MIN_VALID_JPG_BYTES = 50_000


def jpg_is_valid(jpg_path: Path, heic_path: Optional[Path] = None) -> bool:
    """False when JPG is missing, unreadable, or a failed HEIC conversion."""
    if not jpg_path.exists():
        return False
    if jpg_path.stat().st_size < MIN_VALID_JPG_BYTES:
        if heic_path and heic_path.exists() and heic_path.stat().st_size > MIN_VALID_JPG_BYTES:
            return False
    try:
        import cv2
        img = cv2.imread(str(jpg_path))
        return img is not None and img.size > 0
    except Exception:
        return False


def convert_with_sips(heic_path: Path, jpg_path: Path) -> bool:
    try:
        subprocess.run(
            ["sips", "-s", "format", "jpeg", str(heic_path), "--out", str(jpg_path)],
            check=True,
            capture_output=True,
        )
        return jpg_path.exists() and jpg_path.stat().st_size > 0
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def convert_with_pillow(heic_path: Path, jpg_path: Path) -> bool:
    try:
        from PIL import Image
        import pillow_heif
        pillow_heif.register_heif_opener()
        img = Image.open(heic_path)
        img.convert("RGB").save(jpg_path, "JPEG", quality=90)
        return jpg_path.exists() and jpg_path.stat().st_size > 0
    except ImportError:
        return False
    except Exception:
        return False


def convert_heic_file(heic_path: Path, force: bool = False) -> bool:
    jpg_path = heic_path.with_suffix(".jpg")
    if not force and jpg_is_valid(jpg_path, heic_path):
        return False
    if jpg_path.exists():
        jpg_path.unlink()
    ok = convert_with_sips(heic_path, jpg_path) or convert_with_pillow(heic_path, jpg_path)
    if ok and jpg_is_valid(jpg_path, heic_path):
        return True
    if jpg_path.exists():
        jpg_path.unlink()
    return False


def prepare_watchlist_images(watchlist_dir: Optional[Path] = None) -> int:
    """Convert HEIC files and repair corrupt JPG stubs. Returns conversion count."""
    root = watchlist_dir or KNOWN_DIR
    if not root.exists():
        return 0

    converted = 0
    for ext in ("*.HEIC", "*.heic", "*.HEIF", "*.heif"):
        for heic_path in root.rglob(ext):
            jpg_path = heic_path.with_suffix(".jpg")
            force = jpg_path.exists() and not jpg_is_valid(jpg_path, heic_path)
            if convert_heic_file(heic_path, force=force or not jpg_path.exists()):
                converted += 1
                print(f"Converted: {heic_path.name} → {jpg_path.name}")
    return converted


def main():
    if not KNOWN_DIR.exists():
        print(f"data/watchlist/ not found at {KNOWN_DIR}")
        return

    converted = prepare_watchlist_images()
    if converted:
        print(f"Done — converted/repaired {converted} image(s). Run: python3 scripts/ingest_watchlist.py")
    else:
        print("No HEIC files needed conversion (or sips/Pillow unavailable)")


if __name__ == "__main__":
    main()
