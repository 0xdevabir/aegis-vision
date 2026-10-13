import os
import secrets
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import bcrypt
from sqlalchemy.orm import Session
from backend.db.database import get_db
from backend.models.user import User

# No built-in fallback: with SECRET_KEY unset, a random per-process key is used, so tokens
# cannot be forged with a value read from the source (they just stop working on restart).
SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_urlsafe(48)
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

security = HTTPBearer(auto_error=False)


def _to_bytes(password: str) -> bytes:
    # bcrypt limit is 72 bytes
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_to_bytes(plain), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def issue_token(user: User) -> str:
    """Token bound to the user's current token_version (see revoke_tokens)."""
    return create_access_token({"user_id": user.id, "role": user.role, "tv": user.token_version or 0})


def revoke_tokens(user: User) -> None:
    """Invalidate every token already issued to this user (password change, demotion, disable)."""
    user.token_version = (user.token_version or 0) + 1


def user_from_token(token: Optional[str], db: Session) -> User:
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    # Disabled accounts fall through: both callers reject them with their own "disabled" answer.
    if user.is_active and payload.get("tv", 0) != (user.token_version or 0):
        raise HTTPException(status_code=401, detail="Session revoked. Sign in again.")
    return user


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    user = user_from_token(credentials.credentials if credentials else request.query_params.get("token"), db)
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")   # applies to every role guard
    return user


# National-security role matrix (least privilege → most)
ROLES_OPS = frozenset({"admin", "supervisor", "operator", "police", "investigator"})
ROLES_COMMAND = frozenset({"admin", "supervisor"})
ROLES_ADMIN = frozenset({"admin"})
VALID_ROLES = frozenset({
    "admin", "supervisor", "operator", "police", "investigator", "viewer",
})


def operator_or_admin(user: User = Depends(get_current_user)) -> User:
    """Any operational role can view alerts, evidence, cameras, analytics."""
    if user.role not in ROLES_OPS:
        raise HTTPException(status_code=403, detail="Operational access required")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    return user


def supervisor_or_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in ROLES_COMMAND:
        raise HTTPException(status_code=403, detail="Supervisor or admin access required")
    return user


def admin_only(user: User = Depends(get_current_user)) -> User:
    if user.role not in ROLES_ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
