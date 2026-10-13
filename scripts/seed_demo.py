#!/usr/bin/env python3
"""Create the initial admin user.

Password comes from ADMIN_PASSWORD, or is generated and printed once. There is no
fixed default password.
"""

import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.db.database import SessionLocal, init_db
from backend.models.user import User
from backend.auth.auth import hash_password


def seed_demo_user(reset: bool = False):
    # Seeding a default admin is a development convenience and is skipped in production
    # (use scripts/bootstrap_admin.py there). A password RESET is an explicit operator
    # action that already needs shell access, so it is always allowed.
    if os.getenv("ENVIRONMENT", "development") == "production" and not reset:
        print("Skipping demo user seed in production.")
        return
    init_db()
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == "admin").first()
        if existing and reset:
            password = os.getenv("ADMIN_PASSWORD") or secrets.token_urlsafe(12)
            existing.hashed_password = hash_password(password)
            existing.is_active = True
            db.commit()
            print("Admin password reset:")
            print(f"  username: admin\n  password: {password}" if not os.getenv("ADMIN_PASSWORD")
                  else "  password: (from ADMIN_PASSWORD)")
            return
        if existing:
            print("User 'admin' already exists; password unchanged.")
            print("  Forgot it? Run: python scripts/seed_demo.py --reset-password")
            return
        password = os.getenv("ADMIN_PASSWORD") or secrets.token_urlsafe(12)
        generated = not os.getenv("ADMIN_PASSWORD")
        user = User(
            username="admin",
            email="admin@ai-sss.local",
            hashed_password=hash_password(password),
            role="admin",
            is_active=True,
        )
        db.add(user)
        db.commit()
        print("Created admin user:")
        print("  username: admin")
        if generated:
            print(f"  password: {password}   <- generated, shown once; change it after login")
        else:
            print("  password: (from ADMIN_PASSWORD)")
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_user(reset="--reset-password" in sys.argv)
