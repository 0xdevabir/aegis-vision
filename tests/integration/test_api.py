"""FastAPI integration tests."""

import os
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_aegis_api.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only-32chars")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-32-chars!!")
os.environ.setdefault("ENVIRONMENT", "development")

from backend.main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _init_db():
    from backend.db.database import init_db
    init_db()


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("healthy", "degraded")


def test_login_and_me():
    from backend.db.database import SessionLocal
    from backend.models.user import User
    from backend.auth.auth import hash_password

    db = SessionLocal()
    if not db.query(User).filter(User.username == "testop").first():
        db.add(User(username="testop", email="t@t.local", hashed_password=hash_password("pass1234"), role="operator", is_active=True))
        db.commit()
    db.close()

    r = client.post("/api/v1/auth/login", json={"username": "testop", "password": "pass1234"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "testop"


def test_config_thresholds_requires_auth():
    r = client.get("/api/v1/config/thresholds/all")
    assert r.status_code == 401
