"""
Face-matching accuracy sweep: genuine vs impostor distances -> FAR/FRR per tolerance.

Layout (one folder per identity, 2+ photos each):
    data/watchlist/<ID>/*.jpg        enrolled criminals (genuine pairs)
    data/eval/civilians/<NAME>/*.jpg people who must NEVER match (impostors)

Usage:
    python scripts/evaluate_faces.py
"""

import sys
from itertools import combinations
from pathlib import Path

import face_recognition
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from paths import WATCHLIST_DIR  # noqa: E402

EVAL_DIR = ROOT / "data" / "eval" / "civilians"
SUFFIXES = {".jpg", ".jpeg", ".png"}


def _encode_folder(folder: Path):
    encs = []
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() in SUFFIXES:
            img = face_recognition.load_image_file(str(p))
            found = face_recognition.face_encodings(img, num_jitters=1)
            if len(found) == 1:
                encs.append(found[0])
    return encs


def _load(root: Path):
    people = {}
    if root.is_dir():
        for d in sorted(root.iterdir()):
            if d.is_dir():
                encs = _encode_folder(d)
                if encs:
                    people[d.name] = encs
    return people


def main():
    enrolled = _load(Path(WATCHLIST_DIR))
    civilians = _load(EVAL_DIR)
    genuine = [float(np.linalg.norm(a - b)) for e in enrolled.values() for a, b in combinations(e, 2)]
    impostor = [float(np.linalg.norm(a - b))
                for ne, e in enrolled.items() for nc, c in {**enrolled, **civilians}.items() if nc != ne
                for a in e for b in c]
    if not genuine or not impostor:
        sys.exit("Need >=2 photos per enrolled person and at least one other identity (add data/eval/civilians/*).")
    print(f"genuine pairs={len(genuine)} impostor pairs={len(impostor)}")
    print(f"{'tol':>5} {'FRR':>7} {'FAR':>7}")
    best = None
    for tol in np.arange(0.30, 0.66, 0.025):
        frr = float(np.mean([d > tol for d in genuine]))
        far = float(np.mean([d <= tol for d in impostor]))
        print(f"{tol:5.3f} {frr:7.1%} {far:7.2%}")
        if far == 0 and (best is None or tol > best):
            best = tol
    print(f"\nLargest tolerance with 0 false accepts: {best if best is not None else 'none (add more data)'}")


if __name__ == "__main__":
    main()
