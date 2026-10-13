import json
import uuid
from datetime import datetime
from typing import List, Optional

from starlette.concurrency import run_in_threadpool
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.auth.auth import admin_only, operator_or_admin, supervisor_or_admin
from backend.auth.guards import viewer_user
from backend.db.database import get_db
from backend.models.audit_log import AuditLog
from backend.models.evidence import Evidence
from backend.models.face_encoding import FaceEncoding
from backend.models.known_person import KnownPerson
from backend.models.person_image import PersonImage
from backend.models.user import User
from backend.services import face_service as fs

router = APIRouter(prefix="/faces", tags=["faces"])

CATEGORIES = {"criminal", "person_of_interest", "missing_person", "civilian"}
STATUSES = {"wanted", "convicted", "suspect", "cleared", "unknown"}
MAX_FILES = 30


class FaceEncodingResponse(BaseModel):
    id: int
    person_id: str
    person_name: Optional[str]
    encoding_version: str

    class Config:
        from_attributes = True


class KnownPersonResponse(BaseModel):
    id: int
    person_id: str
    name: str
    category: str
    criminal_status: str
    threat_level: int
    notes: Optional[str]
    image_count: int = 0
    encoding_count: int = 0
    first_image_id: Optional[int] = None
    created_at: Optional[datetime] = None


class PersonPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    category: Optional[str] = None
    criminal_status: Optional[str] = None
    threat_level: Optional[int] = Field(default=None, ge=0, le=10)
    notes: Optional[str] = None


def _audit(db: Session, user: User, action: str, resource_id: str, details: dict, request: Request = None):
    db.add(AuditLog(
        user_id=user.id, username=user.username, action=action, resource="face",
        resource_id=resource_id, details=json.dumps(details),
        ip_address=request.client.host if request and request.client else None,
    ))


def _validate_meta(category: Optional[str], status: Optional[str]):
    if category is not None and category not in CATEGORIES:
        raise HTTPException(422, f"category must be one of {sorted(CATEGORIES)}")
    if status is not None and status not in STATUSES:
        raise HTTPException(422, f"criminal_status must be one of {sorted(STATUSES)}")
    if category in ("civilian", "missing_person") and status in ("wanted", "convicted", "suspect"):
        raise HTTPException(422, f"criminal_status '{status}' is not valid for category '{category}'")


def _get_person(db: Session, person_id: str) -> KnownPerson:
    p = db.query(KnownPerson).filter(KnownPerson.person_id == person_id).first()
    if not p:
        raise HTTPException(404, "Person not found")
    return p


def _serialize(db: Session, people: List[KnownPerson]) -> List[dict]:
    ids = [p.id for p in people]
    imgs, encs, firsts = {}, {}, {}
    if ids:
        imgs = dict(db.query(PersonImage.person_id, func.count(PersonImage.id))
                    .filter(PersonImage.person_id.in_(ids)).group_by(PersonImage.person_id).all())
        encs = dict(db.query(FaceEncoding.person_id, func.count(FaceEncoding.id))
                    .filter(FaceEncoding.person_id.in_(ids)).group_by(FaceEncoding.person_id).all())
        firsts = dict(db.query(PersonImage.person_id, func.min(PersonImage.id))
                      .filter(PersonImage.person_id.in_(ids)).group_by(PersonImage.person_id).all())
    return [{
        "id": p.id, "person_id": p.person_id, "name": p.name, "category": p.category,
        "criminal_status": p.criminal_status or "unknown", "threat_level": p.threat_level or 0,
        "notes": p.notes, "image_count": imgs.get(p.id, 0), "encoding_count": encs.get(p.id, 0),
        "first_image_id": firsts.get(p.id), "created_at": p.created_at,
    } for p in people]


async def _read_uploads(files: List[UploadFile]) -> List[tuple]:
    if not files:
        raise HTTPException(400, "At least one image is required")
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"At most {MAX_FILES} images per request")
    out = []
    for f in files:
        out.append((f.filename, await f.read(fs.MAX_IMAGE_BYTES + 1)))
    return out


def _enroll_all(db: Session, person: KnownPerson, uploads: List[tuple]) -> List[dict]:
    tol = fs.get_tolerance()
    results = []
    for filename, data in uploads:
        try:
            results.append({"status": "enrolled", **fs.enroll_image(db, person, data, filename, tol)})
        except fs.FaceError as e:
            if e.status == 503:
                raise HTTPException(503, str(e))
            results.append({"status": "rejected", "filename": filename, "reason": str(e)})
    return results


@router.get("/", response_model=list[FaceEncodingResponse])
def list_encodings(skip: int = 0, limit: int = 100, db: Session = Depends(get_db),
                   user: User = Depends(operator_or_admin)):
    return db.query(FaceEncoding).offset(skip).limit(limit).all()


@router.get("/known-persons", response_model=list[KnownPersonResponse])
def list_known_persons(skip: int = 0, limit: int = 100, category: Optional[str] = None,
                       q: Optional[str] = Query(default=None, max_length=100),
                       db: Session = Depends(get_db), user: User = Depends(operator_or_admin)):
    query = db.query(KnownPerson)
    if category:
        query = query.filter(KnownPerson.category == category)
    if q:
        like = f"%{q}%"
        query = query.filter(KnownPerson.name.ilike(like) | KnownPerson.person_id.ilike(like))
    return _serialize(db, query.order_by(KnownPerson.id.desc()).offset(skip).limit(limit).all())


@router.post("/persons", status_code=201)
async def enroll_person(
    request: Request,
    name: str = Form(..., min_length=1, max_length=100),
    category: str = Form(...),
    criminal_status: str = Form("unknown"),
    threat_level: int = Form(0, ge=0, le=10),
    notes: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(supervisor_or_admin),
):
    """Create a person and enroll their face photos (>=1 must contain exactly one face)."""
    _validate_meta(category, criminal_status)
    uploads = await _read_uploads(files)
    person = KnownPerson(person_id=f"P-{uuid.uuid4().hex[:8].upper()}", name=name.strip(),
                         category=category, criminal_status=criminal_status,
                         threat_level=threat_level, notes=notes, created_by=user.id)
    db.add(person)
    db.flush()
    results = await run_in_threadpool(_enroll_all, db, person, uploads)
    if not any(r["status"] == "enrolled" for r in results):
        db.rollback()
        raise HTTPException(422, detail={"message": "No usable face found in any image", "results": results})
    _audit(db, user, "FACE_ENROLL", person.person_id,
           {"name": person.name, "category": category,
            "enrolled": sum(r["status"] == "enrolled" for r in results)}, request)
    db.commit()
    return {"person": _serialize(db, [person])[0], "results": results}


@router.get("/persons/{person_id}")
def person_detail(person_id: str, db: Session = Depends(get_db),
                  user: User = Depends(operator_or_admin)):
    p = _get_person(db, person_id)
    images = db.query(PersonImage.id, PersonImage.filename, PersonImage.created_at) \
        .filter(PersonImage.person_id == p.id).order_by(PersonImage.id).all()
    return {**_serialize(db, [p])[0],
            "images": [{"id": i.id, "filename": i.filename, "created_at": i.created_at} for i in images]}


@router.patch("/persons/{person_id}")
def update_person(person_id: str, body: PersonPatch, request: Request,
                  db: Session = Depends(get_db), user: User = Depends(supervisor_or_admin)):
    p = _get_person(db, person_id)
    changes = body.model_dump(exclude_unset=True)
    for required in ("name", "category", "criminal_status"):
        if required in changes and changes[required] is None:
            raise HTTPException(422, f"{required} cannot be null")
    _validate_meta(changes.get("category", p.category), changes.get("criminal_status", p.criminal_status))
    for k, v in changes.items():
        setattr(p, k, v)
    _audit(db, user, "FACE_UPDATE", p.person_id, changes, request)
    db.commit()
    return _serialize(db, [p])[0]


@router.delete("/persons/{person_id}")
def delete_person(person_id: str, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(admin_only)):
    p = _get_person(db, person_id)
    # Evidence keeps person_name; only the link is cleared (custody chain stays intact).
    db.query(Evidence).filter(Evidence.person_id == p.id).update({Evidence.person_id: None})
    db.query(FaceEncoding).filter(FaceEncoding.person_id == p.id).delete()
    db.query(PersonImage).filter(PersonImage.person_id == p.id).delete()
    _audit(db, user, "FACE_DELETE", p.person_id, {"name": p.name}, request)
    db.delete(p)
    db.commit()
    return {"status": "deleted"}


@router.post("/persons/{person_id}/images")
async def add_images(person_id: str, request: Request, files: List[UploadFile] = File(...),
                     db: Session = Depends(get_db), user: User = Depends(supervisor_or_admin)):
    p = _get_person(db, person_id)
    results = await run_in_threadpool(_enroll_all, db, p, await _read_uploads(files))
    n = sum(r["status"] == "enrolled" for r in results)
    if n:
        _audit(db, user, "FACE_ENROLL", p.person_id, {"added": n}, request)
    db.commit()
    return {"person": _serialize(db, [p])[0], "results": results}


@router.get("/images/{image_id}")
def get_image(image_id: int, token: Optional[str] = Query(default=None), db: Session = Depends(get_db)):
    """Stored enrollment photo (JWT via query param so <img> tags work)."""
    viewer_user(token, db)
    img = db.query(PersonImage).filter(PersonImage.id == image_id).first()
    if not img:
        raise HTTPException(404, "Image not found")
    return Response(content=img.image_data, media_type="image/jpeg",
                    headers={"Cache-Control": "private, no-store"})


@router.delete("/images/{image_id}")
def delete_image(image_id: int, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(supervisor_or_admin)):
    img = db.query(PersonImage).filter(PersonImage.id == image_id).first()
    if not img:
        raise HTTPException(404, "Image not found")
    remaining = db.query(func.count(PersonImage.id)).filter(PersonImage.person_id == img.person_id).scalar()
    if remaining <= 1:
        raise HTTPException(409, "Cannot delete the last photo; delete the person instead")
    db.query(FaceEncoding).filter(FaceEncoding.image_id == img.id).delete()
    # Legacy ingest rows have image_id NULL: if the person has more encodings than photos, drop the surplus
    # so a deleted photo can never keep matching.
    left = db.query(FaceEncoding).filter(FaceEncoding.person_id == img.person_id).order_by(FaceEncoding.id).all()
    unlinked = [e for e in left if e.image_id is None]
    surplus = len(left) - (remaining - 1)
    for e in unlinked[:max(0, min(surplus, len(unlinked)))]:
        db.delete(e)
    _audit(db, user, "FACE_IMAGE_DELETE", str(img.id), {"person": img.person.person_id}, request)
    db.delete(img)
    db.commit()
    return {"status": "deleted"}


@router.post("/verify")
async def verify_face(
    request: Request,
    file: UploadFile = File(...),
    person_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(operator_or_admin),
):
    """Match a probe photo against stored records.

    Without `person_id`: 1:N search -> ranked candidates per detected face.
    With `person_id`: 1:1 check -> does the photo match that specific record?
    Result `status`: match | no_match | no_face. Every call is audit-logged.
    """
    target = _get_person(db, person_id) if person_id else None
    data = await file.read(fs.MAX_IMAGE_BYTES + 1)
    tol = fs.get_tolerance()
    try:
        result = fs.verify_bytes(db, data, target, tol)
    except fs.FaceError as e:
        raise HTTPException(e.status, str(e))
    best = result["best_match"]
    _audit(db, user, "FACE_VERIFY", (best or {}).get("person_id") or (target.person_id if target else "-"),
           {"status": result["status"], "mode": result["mode"], "faces": result["face_count"],
            "best_distance": (best or {}).get("distance"), "tolerance": tol,
            "filename": file.filename}, request)
    db.commit()
    return result


@router.post("/verify-evidence/{evidence_id}")
def verify_evidence(evidence_id: int, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(operator_or_admin)):
    """Check a captured evidence image against enrolled faces: match or no match.

    Tries the subject crop first, then the full frame. Also reports what the live
    pipeline recorded for this evidence so a reviewer can see whether the two agree.
    """
    ev = db.query(Evidence).filter(Evidence.id == evidence_id).first()
    if not ev:
        raise HTTPException(404, "Evidence not found")
    tol = fs.get_tolerance()
    result, source = None, None
    for kind, blob in (("subject crop", ev.roi_data), ("full frame", ev.frame_data)):
        if not blob:
            continue
        if ev.encrypted:
            from backend.utils.encryption import EncryptionManager
            blob = EncryptionManager().decrypt(blob)
        try:
            attempt = fs.verify_bytes(db, blob, None, tol)
        except fs.FaceError as e:
            if e.status == 503:
                raise HTTPException(503, str(e))
            continue
        if result is None or attempt["status"] != "no_face":
            result, source = attempt, kind
        if attempt["status"] != "no_face":
            break
    if result is None:
        raise HTTPException(404, "No image stored for this evidence")
    best = result["best_match"]
    recorded = ev.person_name if ev.person_name and ev.person_name != "Unknown" else None
    matched_name = best and best["person_id"]
    result.update({
        "evidence_id": ev.id, "source": source,
        "recorded_identity": recorded,
        "agrees_with_live_id": None if not recorded else (matched_name == recorded or (best or {}).get("name") == recorded),
    })
    _audit(db, user, "FACE_VERIFY_EVIDENCE", str(ev.id),
           {"status": result["status"], "source": source,
            "best": matched_name, "distance": (best or {}).get("distance")}, request)
    db.commit()
    return result


@router.post("/encode")
def reencode_faces(db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    """Rebuild every embedding from stored photos (e.g. after a model change)."""
    persons = db.query(KnownPerson).all()
    results = {"encoded": 0, "errors": 0}
    for person in persons:
        images = db.query(PersonImage).filter(PersonImage.person_id == person.id).all()
        if not images:
            continue  # keep legacy encodings that have no stored photo
        fresh = []
        for img in images:
            try:
                rgb = fs.decode_image(img.image_data)
                enc = fs.encode_single_face(rgb)
                fresh.append(FaceEncoding(person_id=person.id, image_id=img.id,
                                          encoding=FaceEncoding.serialize_encoding(enc)))
            except fs.FaceError as e:
                if e.status == 503:
                    raise HTTPException(503, str(e))
                results["errors"] += 1
        if fresh:
            db.query(FaceEncoding).filter(FaceEncoding.person_id == person.id).delete()
            db.add_all(fresh)
            results["encoded"] += len(fresh)
    db.commit()
    return results
