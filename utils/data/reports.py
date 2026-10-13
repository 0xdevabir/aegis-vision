from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from backend.db.database import SessionLocal
from backend.models.evidence import Evidence
from backend.models.alert import Alert


class ReportGenerator:
    def __init__(self):
        self.db: Session = SessionLocal()

    def close(self):
        self.db.close()

    def generate_incident_report(self, hours: int = 24) -> dict:
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        evidence_records = self.db.query(Evidence).filter(Evidence.timestamp >= cutoff).all()
        alert_records = self.db.query(Alert).filter(Alert.timestamp >= cutoff).all()
        criminals = [e for e in evidence_records if e.is_criminal]
        weapons = [e for e in evidence_records if e.weapon_present]
        suspicious = [e for e in evidence_records if e.is_suspicious and not e.is_criminal and not e.weapon_present]
        return {
            "report_type": "incident",
            "period_hours": hours,
            "generated_at": datetime.utcnow().isoformat(),
            "summary": {
                "total_events": len(evidence_records),
                "criminal_detections": len(criminals),
                "weapon_detections": len(weapons),
                "suspicious_activities": len(suspicious),
                "alerts_triggered": len(alert_records),
            },
            "breakdown": {
                "criminals": [
                    {"name": e.person_name, "location": e.camera_location, "time": e.timestamp.isoformat()}
                    for e in criminals[:50]
                ],
                "weapons": [
                    {"location": e.camera_location, "time": e.timestamp.isoformat()}
                    for e in weapons[:50]
                ],
            },
        }

    def generate_evidence_bundle(self, evidence_ids: list[int]) -> dict:
        records = self.db.query(Evidence).filter(Evidence.id.in_(evidence_ids)).all()
        return {
            "bundle_id": f"bundle_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            "generated_at": datetime.utcnow().isoformat(),
            "evidence_count": len(records),
            "items": [
                {
                    "id": e.id,
                    "timestamp": e.timestamp.isoformat(),
                    "location": e.camera_location,
                    "person": e.person_name,
                    "category": e.category,
                    "has_frame_data": e.frame_data is not None,
                    "has_roi_data": e.roi_data is not None,
                }
                for e in records
            ],
        }


def generate_report(hours: int = 24) -> dict:
    gen = ReportGenerator()
    try:
        return gen.generate_incident_report(hours)
    finally:
        gen.close()
