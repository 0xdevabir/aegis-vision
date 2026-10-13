from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel, field_validator
from backend.models.audit_log import AuditLog
from backend.db.database import get_db
from backend.models.user import User
from backend.auth.auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, admin_only, operator_or_admin, VALID_ROLES, ROLES_OPS,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    role: str


MIN_PASSWORD = 10
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 10


def _check_password(v: str) -> str:
    if len(v) < MIN_PASSWORD:
        raise ValueError(f"Password must be at least {MIN_PASSWORD} characters")
    if v.isalpha() or v.isdigit():
        raise ValueError("Password must mix letters and digits or symbols")
    return v


def _audit(db: Session, action: str, user: Optional[User], resource_id: str, details: str, request: Request = None):
    db.add(AuditLog(
        user_id=user.id if user else None, username=user.username if user else None,
        action=action, resource="user", resource_id=resource_id, details=details,
        ip_address=request.client.host if request and request.client else None,
    ))


class UserCreate(BaseModel):
    username: str
    email: str
    password: str

    @field_validator("password")
    @classmethod
    def _pw(cls, v):
        return _check_password(v)

    role: str = "viewer"
    phone: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    phone: Optional[str] = None

    class Config:
        from_attributes = True


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    now = datetime.now(timezone.utc)
    if user and user.locked_until:
        until = user.locked_until if user.locked_until.tzinfo else user.locked_until.replace(tzinfo=timezone.utc)
        if until > now:
            mins = int((until - now).total_seconds() // 60) + 1
            raise HTTPException(status_code=429, detail=f"Account locked after repeated failures. Try again in {mins} min.")
    if not user or not verify_password(req.password, user.hashed_password):
        if user:
            user.failed_attempts = (user.failed_attempts or 0) + 1
            if user.failed_attempts >= MAX_FAILED_LOGINS:
                user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
                user.failed_attempts = 0
        _audit(db, "LOGIN_FAILED", user, req.username, "invalid credentials", request)
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        _audit(db, "LOGIN_DENIED", user, user.username, "account disabled", request)
        db.commit()
        raise HTTPException(status_code=403, detail="Account disabled")
    user.failed_attempts = 0
    user.locked_until = None
    _audit(db, "LOGIN", user, user.username, "ok", request)
    db.commit()
    token = create_access_token({"user_id": user.id, "role": user.role})
    return LoginResponse(access_token=token, user_id=user.id, role=user.role)


@router.post("/users", response_model=UserResponse)
def create_user(req: UserCreate, request: Request, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    if req.role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Allowed: {', '.join(sorted(VALID_ROLES))}",
        )
    existing = db.query(User).filter(
        (User.username == req.username) | (User.email == req.email)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username or email already exists")
    user = User(
        username=req.username,
        email=req.email,
        hashed_password=hash_password(req.password),
        role=req.role,
        phone=(req.phone or "").strip() or None,
    )
    db.add(user)
    db.flush()
    _audit(db, "USER_CREATE", admin, user.username, f"role={user.role}", request)
    db.commit()
    db.refresh(user)
    return user


class ChangePassword(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _pw(cls, v):
        return _check_password(v)


@router.post("/change-password")
def change_password(body: ChangePassword, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.hashed_password = hash_password(body.new_password)
    _audit(db, "PASSWORD_CHANGE", user, user.username, "self-service", request)
    db.commit()
    return {"status": "changed"}


class UserPatch(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    phone: Optional[str] = None
    new_password: Optional[str] = None

    @field_validator("new_password")
    @classmethod
    def _pw(cls, v):
        return _check_password(v) if v is not None else v


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(user_id: int, body: UserPatch, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(admin_only)):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    changes = body.model_dump(exclude_unset=True)
    if "role" in changes and changes["role"] not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Allowed: {', '.join(sorted(VALID_ROLES))}")
    if target.id == admin.id and (changes.get("is_active") is False or changes.get("role", "admin") != "admin"):
        raise HTTPException(status_code=400, detail="You cannot disable or demote your own account")
    if "role" in changes:
        target.role = changes["role"]
    if "is_active" in changes and changes["is_active"] is not None:
        target.is_active = changes["is_active"]
        if target.is_active:
            target.failed_attempts, target.locked_until = 0, None
    if "phone" in changes:
        target.phone = (changes["phone"] or "").strip() or None
    if changes.get("new_password"):
        target.hashed_password = hash_password(changes["new_password"])
    shown = {k: ("***" if k == "new_password" else v) for k, v in changes.items()}
    _audit(db, "USER_UPDATE", admin, target.username, str(shown), request)
    db.commit()
    db.refresh(target)
    return target


@router.post("/refresh", response_model=LoginResponse)
def refresh_token(user: User = Depends(get_current_user)):
    """Sliding session: a still-valid token buys a fresh one, so an open control-room screen never expires."""
    return LoginResponse(access_token=create_access_token({"user_id": user.id, "role": user.role}),
                         user_id=user.id, role=user.role)


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)):
    return user


class Assignee(BaseModel):
    id: int
    username: str
    role: str


@router.get("/assignees", response_model=list[Assignee])
def list_assignees(db: Session = Depends(get_db), user: User = Depends(operator_or_admin)):
    """Active operational users an incident can be assigned to (no email/phone)."""
    return (db.query(User).filter(User.is_active == True, User.role.in_(sorted(ROLES_OPS)))  # noqa: E712
            .order_by(User.username).all())


@router.get("/users", response_model=list[UserResponse])
def list_users(db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    return db.query(User).all()

