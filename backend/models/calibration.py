"""Ground-truth labels for model calibration / false-alarm analysis."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float, Index
from sqlalchemy.sql import func
from backend.db.database import Base


class DetectionLabel(Base):
    """
    Operator-confirmed label against an alert or evidence record.
    true_positive | false_positive | true_negative | false_negative
    """
    __tablename__ = "detection_labels"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, nullable=True, index=True)
    evidence_id = Column(Integer, nullable=True, index=True)
    detection_type = Column(String(40), nullable=False, index=True)
    predicted_label = Column(String(40), nullable=True)
    ground_truth = Column(String(40), nullable=False)  # TP|FP|TN|FN or true_positive etc.
    confidence = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    labeled_by = Column(String(80), nullable=True)
    labeled_by_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        Index("idx_label_type_truth", "detection_type", "ground_truth"),
    )
