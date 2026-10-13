"""
Ingest watchlist face images into PostgreSQL.

Reads images from data/watchlist/ + optional manifest.json metadata,
generates face encodings, and stores encoding + raw image bytes in the DB.

Usage:
    python3 scripts/ingest_watchlist.py
"""

import json
import sys
from pathlib import Path

import cv2
import face_recognition

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.db.database import SessionLocal, init_db
from backend.models.known_person import KnownPerson
from backend.models.person_image import PersonImage
from backend.models.face_encoding import FaceEncoding
from paths import WATCHLIST_DIR
from scripts.convert_heic import prepare_watchlist_images, jpg_is_valid

KNOWN_DIR = WATCHLIST_DIR
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".heif"}


def _read_image_bytes(path: str) -> bytes:
    img = cv2.imread(path)
    if img is None:
        return b""
    success, buffer = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buffer.tobytes() if success else b""


def _iter_watchlist_images(person_dir: Path):
    """Yield one readable image path per photo (prefer valid JPG over HEIC)."""
    seen_stems = set()
    for img_file in sorted(person_dir.iterdir()):
        if not img_file.is_file():
            continue
        suffix = img_file.suffix.lower()
        if suffix not in IMAGE_SUFFIXES:
            continue

        stem = img_file.stem
        if stem in seen_stems:
            continue

        if suffix in {".heic", ".heif"}:
            jpg_path = img_file.with_suffix(".jpg")
            if jpg_is_valid(jpg_path, img_file):
                seen_stems.add(stem)
                yield jpg_path
            continue

        heic_path = img_file.with_suffix(".HEIC")
        if not heic_path.exists():
            heic_path = img_file.with_suffix(".heic")
        if jpg_is_valid(img_file, heic_path if heic_path.exists() else None):
            seen_stems.add(stem)
            yield img_file


def _load_manifest() -> dict:
    manifest_path = KNOWN_DIR / "manifest.json"
    if not manifest_path.exists():
        return {}
    with open(manifest_path) as f:
        data = json.load(f)
    return {p["person_id"]: p for p in data.get("persons", [])}


def _folder_metadata(folder_name: str):
    parts = folder_name.split("_", 2)
    if len(parts) >= 3:
        name = parts[2].replace("_", " ")
        category = "criminal" if parts[0].upper() == "CRIMINAL" else "civilian"
    else:
        name = folder_name
        category = "civilian"
    return {
        "name": name,
        "category": category,
        "criminal_status": "unknown" if category == "criminal" else "cleared",
        "threat_level": 5 if category == "criminal" else 0,
        "notes": None,
    }


def ingest():
    if not KNOWN_DIR.exists():
        print(f"❌ watchlist directory not found at {KNOWN_DIR}")
        return

    print("Preparing watchlist images (HEIC → JPG)...")
    repaired = prepare_watchlist_images()
    if repaired:
        print(f"✓ Converted/repaired {repaired} image(s)")

    init_db()
    db = SessionLocal()
    manifest = _load_manifest()
    if manifest:
        print(f"✓ Loaded {len(manifest)} entries from manifest.json")

    total_persons = 0
    total_images = 0
    total_encodings = 0

    try:
        for person_dir in sorted(KNOWN_DIR.iterdir()):
            if not person_dir.is_dir():
                continue

            folder_name = person_dir.name
            meta = manifest.get(folder_name, _folder_metadata(folder_name))

            print(f"\n[{folder_name}]")

            person = db.query(KnownPerson).filter(
                KnownPerson.person_id == folder_name
            ).first()
            if not person:
                person = KnownPerson(
                    person_id=folder_name,
                    name=meta["name"],
                    category=meta["category"],
                    criminal_status=meta["criminal_status"],
                    threat_level=meta["threat_level"],
                    notes=meta.get("notes"),
                )
                db.add(person)
                db.commit()
                db.refresh(person)
                total_persons += 1
                print(f"  ✓ Created person record: {meta['name']}")

            for img_file in _iter_watchlist_images(person_dir):
                img_path = str(img_file)

                existing_img = db.query(PersonImage).filter(
                    PersonImage.person_id == person.id,
                    PersonImage.filename == img_file.name,
                ).first()
                if existing_img:
                    print(f"  ↷ Skipping (already in DB): {img_file.name}")
                    continue

                try:
                    image = face_recognition.load_image_file(img_path)
                    boxes = face_recognition.face_locations(image, model="hog")
                    if not boxes:
                        print(f"  ✗ No face found in: {img_file.name}")
                        continue
                    
                    if len(boxes) > 1:
                        print(f"  ⚠ Multiple faces found in {img_file.name}, taking the largest one.")
                        # boxes are (top, right, bottom, left)
                        areas = [(b[2]-b[0]) * (b[1]-b[3]) for b in boxes]
                        best_idx = areas.index(max(areas))
                        boxes = [boxes[best_idx]]

                    encodings = face_recognition.face_encodings(image, boxes, num_jitters=5)
                except Exception as e:
                    print(f"  ✗ Error processing {img_file.name}: {e}")
                    continue

                if not encodings:
                    print(f"  ✗ No face encoding generated for: {img_file.name}")
                    continue

                enc_record = FaceEncoding(
                    person_id=person.id,
                    encoding=FaceEncoding.serialize_encoding(encodings[0]),
                )
                db.add(enc_record)
                total_encodings += 1

                image_bytes = _read_image_bytes(img_path)
                if image_bytes:
                    img_record = PersonImage(
                        person_id=person.id,
                        image_data=image_bytes,
                        image_type="face",
                        filename=img_file.name,
                    )
                    db.add(img_record)
                    total_images += 1

                try:
                    db.commit()
                    print(f"  ✓ Encoded + stored: {img_file.name}")
                except Exception as e:
                    db.rollback()
                    print(f"  ✗ DB error for {img_file.name}: {e}")

        print(f"\n{'='*50}")
        print("✅ Ingest complete!")
        print(f"   Persons:   {total_persons} created")
        print(f"   Images:    {total_images} stored in DB")
        print(f"   Encodings: {total_encodings} stored in DB")

    except Exception as e:
        print(f"❌ Fatal error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    ingest()

