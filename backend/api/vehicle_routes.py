from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.db.database import get_db
from backend.models.vehicle import LicensePlate, VehicleDetection
from backend.auth.auth import admin_only, operator_or_admin
from backend.models.user import User
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


class LicensePlateCreate(BaseModel):
    plate_number: str
    reason: Optional[str] = None


class LicensePlateResponse(BaseModel):
    id: int
    plate_number: str
    watchlisted: bool
    reason: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/plates", response_model=List[LicensePlateResponse])
def list_plates(
    skip: int = 0,
    limit: int = 100,
    watchlisted_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin)
):
    query = db.query(LicensePlate)
    if watchlisted_only:
        query = query.filter(LicensePlate.watchlisted == True)
    return query.offset(skip).limit(limit).all()


@router.post("/plates", response_model=LicensePlateResponse)
def add_watchlisted_plate(
    plate: LicensePlateCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only)
):
    existing = db.query(LicensePlate).filter(
        LicensePlate.plate_number == plate.plate_number.upper()
    ).first()

    if existing:
        existing.watchlisted = True
        existing.reason = plate.reason
        db.commit()
        return existing

    new_plate = LicensePlate(
        plate_number=plate.plate_number.upper(),
        watchlisted=True,
        reason=plate.reason
    )
    db.add(new_plate)
    db.commit()
    db.refresh(new_plate)
    return new_plate


@router.delete("/plates/{plate_number}")
def remove_watchlisted_plate(
    plate_number: str,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only)
):
    plate = db.query(LicensePlate).filter(
        LicensePlate.plate_number == plate_number.upper()
    ).first()
    if plate:
        plate.watchlisted = False
        db.commit()
        return {"status": "removed"}
    raise HTTPException(status_code=404, detail="Plate not found")


@router.get("/detections")
def list_vehicle_detections(
    skip: int = 0,
    limit: int = 100,
    suspicious_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin)
):
    query = db.query(VehicleDetection)
    if suspicious_only:
        query = query.filter(VehicleDetection.is_suspicious == True)
    return query.order_by(VehicleDetection.timestamp.desc()).offset(skip).limit(limit).all()
