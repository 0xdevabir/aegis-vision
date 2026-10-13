import os
import json
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session
from backend.db.database import SessionLocal
from backend.models.evidence import Evidence


class RetentionPolicy:
    def __init__(self, config: dict = None):
        cfg = config or {}
        self.enabled = cfg.get("enabled", False)
        self.evidence_days = cfg.get("evidence_days", 90)
        self.archive_path = Path(cfg.get("archive_path", "evidence/archive"))
        self.dry_run = cfg.get("dry_run", False)

    def run(self) -> dict:
        if not self.enabled:
            return {"status": "disabled", "message": "Retention policy is disabled"}

        cutoff = datetime.utcnow() - timedelta(days=self.evidence_days)
        stats = {"deleted": 0, "archived": 0, "errors": 0, "freed_bytes": 0}

        db = SessionLocal()
        try:
            expired = (
                db.query(Evidence)
                .filter(Evidence.timestamp < cutoff)
                .all()
            )

            for ev in expired:
                try:
                    size = 0
                    if ev.frame_data:
                        size += len(ev.frame_data)
                    if ev.roi_data:
                        size += len(ev.roi_data)

                    if self.dry_run:
                        stats["deleted"] += 1
                        stats["freed_bytes"] += size
                        continue

                    self._archive_or_delete(ev, db)
                    db.delete(ev)
                    db.commit()
                    stats["deleted"] += 1
                    stats["freed_bytes"] += size
                except Exception as e:
                    print(f"Retention error evidence {ev.id}: {e}")
                    stats["errors"] += 1
                    db.rollback()

            return {
                "status": "completed",
                "cutoff": cutoff.isoformat(),
                "retention_days": self.evidence_days,
                **stats,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            db.close()

    def _archive_or_delete(self, ev: Evidence, db: Session):
        if not self.archive_path:
            return
        self.archive_path.mkdir(parents=True, exist_ok=True)
        manifest = {
            "id": ev.id,
            "timestamp": ev.timestamp.isoformat() if ev.timestamp else None,
            "camera_location": ev.camera_location,
            "track_id": ev.track_id,
            "person_name": ev.person_name,
            "is_criminal": ev.is_criminal,
            "weapon_present": ev.weapon_present,
            "category": ev.category,
        }
        archive_file = self.archive_path / f"evidence_{ev.id}.json"
        with open(archive_file, "w") as f:
            json.dump(manifest, f, indent=2)


def run_retention(dry_run: bool = False) -> dict:
    import yaml
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repo root
    config_path = os.path.join(base_dir, "config", "config.yaml")
    try:
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        retention_cfg = cfg.get("retention", {})
        retention_cfg["dry_run"] = dry_run
        policy = RetentionPolicy(retention_cfg)
        return policy.run()
    except Exception as e:
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import sys
    dry = "--dry-run" in sys.argv
    result = run_retention(dry_run=dry)
    print(json.dumps(result, indent=2))
