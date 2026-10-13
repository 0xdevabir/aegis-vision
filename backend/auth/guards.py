"""Shared request guards: internal pipeline key, media viewer token, path containment."""

import hmac
import os
from pathlib import Path
from typing import Optional

from fastapi import Depends, HTTPException
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from backend.auth.auth import ALGORITHM, ROLES_OPS, SECRET_KEY
from backend.db.database import SessionLocal, get_db
from backend.models.user import User

_INSECURE_INTERNAL_KEYS = {"", "pipeline-internal-key-change-me", "CHANGE_THIS_INTERNAL_API_KEY"}


def internal_key_is_secure() -> bool:
    return os.getenv("INTERNAL_API_KEY", "") not in _INSECURE_INTERNAL_KEYS


def verify_internal_key(key: Optional[str]) -> None:
    """Pipeline→backend auth. Fails closed when the key is unset or a known default."""
    expected = os.getenv("INTERNAL_API_KEY", "")
    if expected in _INSECURE_INTERNAL_KEYS:
        raise HTTPException(status_code=503, detail="Internal API key not configured")
    if not key or not hmac.compare_digest(key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid internal API key")


def viewer_user(token: Optional[str], db: Session) -> User:
    """Resolve the user behind a query-param JWT (for <img>/<video> tags).

    Token is always required, in every environment, and the user must hold an
    operational role and be active.
    """
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = payload.get("user_id")
    user = db.query(User).filter(User.id == user_id).first() if user_id is not None else None
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid token")
    if user.role not in ROLES_OPS:
        raise HTTPException(status_code=403, detail="Operational access required")
    return user


def verify_viewer_token(token: Optional[str]) -> User:
    """Session-less variant for endpoints that don't otherwise hold a DB session."""
    db = SessionLocal()
    try:
        return viewer_user(token, db)
    finally:
        db.close()


def viewer_dep(token: Optional[str] = None, db: Session = Depends(get_db)) -> User:
    return viewer_user(token, db)


def safe_media_path(raw: str, base: Path, root: Path) -> Path:
    """Resolve a stored path and require it to stay inside `base`."""
    p = Path(raw)
    if not p.is_absolute():
        p = root / p
    p = p.resolve()
    if not p.is_relative_to(base.resolve()):
        raise HTTPException(status_code=403, detail="Path outside media directory")
    return p
