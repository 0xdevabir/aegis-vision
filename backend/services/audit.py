"""One place to write audit-trail rows (add to the caller's session; the caller commits)."""
from typing import Optional

from sqlalchemy.orm import Session

from backend.models.audit_log import AuditLog
from backend.models.user import User


def log_audit(db: Session, user: Optional[User], action: str, resource: str, resource_id: str = "",
              details: str = "", request=None) -> None:
    db.add(AuditLog(
        user_id=user.id if user else None, username=user.username if user else "SYSTEM",
        action=action, resource=resource, resource_id=str(resource_id)[:50], details=details,
        ip_address=request.client.host if request is not None and getattr(request, "client", None) else None,
    ))
