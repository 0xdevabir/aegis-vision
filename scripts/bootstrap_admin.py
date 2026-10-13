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
