#!/usr/bin/env python3
"""Sync camera GPS positions from cameras.yaml into PostgreSQL."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.db.database import SessionLocal, init_db
from backend.models.camera import Camera
from utils.config import build_camera_registry


def seed_cameras():
    init_db()
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    registry = build_camera_registry(base_dir)
    db = SessionLocal()
    try:
        for cam_id, info in registry.items():
            existing = db.query(Camera).filter(Camera.camera_id == cam_id).first()
            if existing:
                existing.name = info.get("name", cam_id)
                existing.location = info.get("location")
                existing.lat = info.get("lat")
                existing.lng = info.get("lng")
                existing.rtsp_url = info.get("rtsp_url")
                existing.active = True
            else:
                db.add(Camera(
                    camera_id=cam_id,
                    name=info.get("name", cam_id),
                    location=info.get("location"),
                    lat=info.get("lat"),
                    lng=info.get("lng"),
                    rtsp_url=info.get("rtsp_url"),
                    active=True,
                ))
        db.commit()
        print(f"Synced {len(registry)} camera(s) with GPS to database.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_cameras()
