#!/usr/bin/env python3
"""Create the first admin account if (and only if) there are no users yet.

Unlike seed_demo.py this also works with ENVIRONMENT=production. The password comes from
ADMIN_PASSWORD, or is generated and printed once to the container log. There is no
default password.
"""

import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.auth.auth import hash_password  # noqa: E402
from backend.db.database import SessionLocal  # noqa: E402
from backend.models.user import User  # noqa: E402


DEMO_EMAIL = "demo@aegis.local"   # marks the account this script owns
ROLES = {"viewer", "operator", "police", "investigator", "supervisor", "admin"}


def ensure_demo_user() -> None:
    """Account behind the sign-in page's "Use the demo account" button (DEMO_LOGIN_PASSWORD set).

    The same password is built into the dashboard, so anyone who can open it can sign in:
    for demos only. Unset DEMO_LOGIN_PASSWORD and the account is switched off again.
    """
    username = os.getenv("DEMO_LOGIN_USERNAME") or "demo"
    password = os.getenv("DEMO_LOGIN_PASSWORD", "")
    role = os.getenv("DEMO_LOGIN_ROLE") or "admin"
    db = SessionLocal()
    try:
        if not password:
            stale = db.query(User).filter(User.email == DEMO_EMAIL, User.is_active.is_(True)).all()
            for user in stale:
                user.is_active = False
            if stale:
                db.commit()
                print("[bootstrap] demo login is off: demo account disabled")
            return
        if role not in ROLES:
            print(f"[bootstrap] ERROR: DEMO_LOGIN_ROLE={role!r} is not a role; demo account not created", file=sys.stderr)
            return
        user = db.query(User).filter(User.username == username).first()
        if user and user.email != DEMO_EMAIL:
            # Never take over a real account's password.
            print(f"[bootstrap] ERROR: user {username!r} already exists and is not the demo account; "
                  "pick another DEMO_LOGIN_USERNAME", file=sys.stderr)
            return
        if user:
            user.hashed_password, user.role, user.is_active = hash_password(password), role, True
        else:
            db.add(User(username=username, email=DEMO_EMAIL, hashed_password=hash_password(password),
                        role=role, is_active=True))
        db.commit()
        print(f"[bootstrap] WARNING: demo login is ON ({username!r}, role {role}). "
              "Its password is public in the dashboard; do not expose this deployment.", file=sys.stderr)
    finally:
        db.close()


def main() -> None:
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            print("[bootstrap] users exist — admin not created")
            return
        password = os.getenv("ADMIN_PASSWORD", "")
        generated = not password
        if generated:
            password = secrets.token_urlsafe(14)
        elif len(password) < 10:
            print("[bootstrap] WARNING: ADMIN_PASSWORD is shorter than 10 characters", file=sys.stderr)
        db.add(User(
            username=os.getenv("ADMIN_USERNAME", "admin"),
            email=os.getenv("ADMIN_EMAIL", "admin@aegis.local"),
            hashed_password=hash_password(password),
            role="admin", is_active=True,
        ))
        db.commit()
        print("[bootstrap] admin account created")
        if generated:
            print(f"[bootstrap] username: admin   password: {password}   <- shown once, change it after login")
    finally:
        db.close()


if __name__ == "__main__":
    main()
    ensure_demo_user()
