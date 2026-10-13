"""Model calibration — ground-truth labels + false-alarm metrics."""

import json
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.db.database import get_db
from backend.models.user import User
from backend.models.calibration import DetectionLabel
from backend.models.alert import Alert
from backend.auth.auth import operator_or_admin
from paths import RESULTS_DIR

router = APIRouter(prefix="/calibration", tags=["calibration"])

VALID_TRUTH = {
    "true_positive", "false_positive", "true_negative", "false_negative",
    "TP", "FP", "TN", "FN",
}


class LabelCreate(BaseModel):
    alert_id: Optional[int] = None
    evidence_id: Optional[int] = None
    detection_type: str
    predicted_label: Optional[str] = None
    ground_truth: str
    confidence: Optional[float] = None
    notes: Optional[str] = None


class LabelOut(BaseModel):
    id: int
    alert_id: Optional[int]
    evidence_id: Optional[int]
    detection_type: str
    predicted_label: Optional[str]
    ground_truth: str
    confidence: Optional[float]
    notes: Optional[str]
    labeled_by: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


def _norm(gt: str) -> str:
    m = {"TP": "true_positive", "FP": "false_positive", "TN": "true_negative", "FN": "false_negative"}
    return m.get(gt, gt)


@router.post("/labels", response_model=LabelOut)
def add_label(body: LabelCreate, db: Session = Depends(get_db), user: User = Depends(operator_or_admin)):
    if body.ground_truth not in VALID_TRUTH:
        raise HTTPException(400, f"ground_truth must be one of {sorted(VALID_TRUTH)}")
    row = DetectionLabel(
        alert_id=body.alert_id,
        evidence_id=body.evidence_id,
        detection_type=body.detection_type,
        predicted_label=body.predicted_label,
        ground_truth=_norm(body.ground_truth),
        confidence=body.confidence,
        notes=body.notes,
        labeled_by=user.username,
        labeled_by_id=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/labels", response_model=List[LabelOut])
def list_labels(
    detection_type: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    q = db.query(DetectionLabel)
    if detection_type:
        q = q.filter(DetectionLabel.detection_type == detection_type)
    return q.order_by(desc(DetectionLabel.created_at)).limit(limit).all()


@router.get("/metrics")
def metrics(hours: int = 168, db: Session = Depends(get_db), user: User = Depends(operator_or_admin)):
    """Confusion-matrix style metrics from operator labels + proxy from dismissals."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    labels = db.query(DetectionLabel).filter(DetectionLabel.created_at >= cutoff).all()

    counts = {"true_positive": 0, "false_positive": 0, "true_negative": 0, "false_negative": 0}
    by_type = {}
    for L in labels:
        gt = _norm(L.ground_truth)
        counts[gt] = counts.get(gt, 0) + 1
        bucket = by_type.setdefault(L.detection_type, {"true_positive": 0, "false_positive": 0, "true_negative": 0, "false_negative": 0})
        bucket[gt] = bucket.get(gt, 0) + 1

    tp, fp = counts["true_positive"], counts["false_positive"]
    fn = counts["false_negative"]
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall else None
    far = fp / (tp + fp) if (tp + fp) else None  # false alarm rate among positives

    # Proxy: dismissed alerts without acknowledge as likely FP candidates
    alerts = db.query(Alert).filter(Alert.timestamp >= cutoff).all()
    dismissed = sum(1 for a in alerts if a.dismissed)
    acked = sum(1 for a in alerts if a.acknowledged and not a.dismissed)

    # Latest pipeline eval report if present
    eval_report = None
    eval_path = RESULTS_DIR / "eval.json"
    if eval_path.exists():
        try:
            eval_report = json.loads(eval_path.read_text())
        except Exception:
            pass

    return {
        "period_hours": hours,
        "labeled": len(labels),
        "confusion": counts,
        "by_type": by_type,
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "f1": round(f1, 4) if f1 is not None else None,
        "false_alarm_rate": round(far, 4) if far is not None else None,
        "proxy": {
            "alerts_total": len(alerts),
            "acknowledged": acked,
            "dismissed": dismissed,
            "dismiss_rate": round(dismissed / len(alerts), 4) if alerts else None,
        },
        "pipeline_eval": eval_report,
    }
