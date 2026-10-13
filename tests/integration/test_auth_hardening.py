"""Password policy, lockout, disabled accounts, change-password, user admin and audit trail."""
import os
import types
import sys

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_aegis_api.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only-32chars")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-32-chars!!")
os.environ.setdefault("ENVIRONMENT", "development")
sys.modules.setdefault("face_recognition", types.ModuleType("face_recognition"))

from backend.auth.auth import hash_password  # noqa: E402
from backend.db.database import SessionLocal, init_db  # noqa: E402
from backend.main import app  # noqa: E402
from backend.middleware.rate_limiter import _limiter  # noqa: E402
from backend.models.audit_log import AuditLog  # noqa: E402
from backend.models.user import User  # noqa: E402

client = TestClient(app)
API = "/api/v1/auth"


@pytest.fixture(autouse=True)
def _fresh():
    init_db()
    _limiter._buckets.clear()
    db = SessionLocal()
    db.query(User).filter(User.username.like("ah_%")).delete(synchronize_session=False)
    db.add(User(username="ah_admin", email="ah_admin@t.local", hashed_password=hash_password("AdminPass123"),
                role="admin", is_active=True))
    db.add(User(username="ah_op", email="ah_op@t.local", hashed_password=hash_password("OperPass1234"),
                role="operator", is_active=True))
    db.commit()
    db.close()
    yield
    _limiter._buckets.clear()


def _login(u, p):
    return client.post(f"{API}/login", json={"username": u, "password": p})


def _h(u, p):
    return {"Authorization": f"Bearer {_login(u, p).json()['access_token']}"}


def test_password_policy_on_create():
    h = _h("ah_admin", "AdminPass123")
    r = client.post(f"{API}/users", headers=h, json={"username": "ah_x", "email": "x@t.local", "password": "short1"})
    assert r.status_code == 422
    r = client.post(f"{API}/users", headers=h, json={"username": "ah_x", "email": "x@t.local", "password": "onlyletterslong"})
    assert r.status_code == 422
    r = client.post(f"{API}/users", headers=h, json={"username": "ah_x", "email": "x@t.local",
                                                      "password": "GoodPass12345", "role": "police", "phone": " +8801700000000 "})
    assert r.status_code == 200 and r.json()["phone"] == "+8801700000000"


def test_lockout_after_repeated_failures_and_audit():
    for _ in range(5):
        assert _login("ah_op", "wrong-password").status_code == 401
    r = _login("ah_op", "OperPass1234")                  # correct password, but locked
    assert r.status_code == 429
    db = SessionLocal()
    assert db.query(AuditLog).filter(AuditLog.action == "LOGIN_FAILED", AuditLog.resource_id == "ah_op").count() >= 5
    db.close()


def test_disabled_user_is_rejected_even_with_existing_token():
    admin = _h("ah_admin", "AdminPass123")
    op = _h("ah_op", "OperPass1234")
    assert client.get(f"{API}/me", headers=op).status_code == 200
    db = SessionLocal()
    uid = db.query(User).filter(User.username == "ah_op").first().id
    db.close()
    assert client.patch(f"{API}/users/{uid}", headers=admin, json={"is_active": False}).status_code == 200
    assert client.get(f"{API}/me", headers=op).status_code == 403
    assert _login("ah_op", "OperPass1234").status_code == 403


def test_change_password_and_self_protection():
    op = _h("ah_op", "OperPass1234")
    assert client.post(f"{API}/change-password", headers=op,
                       json={"current_password": "nope", "new_password": "BrandNew12345"}).status_code == 400
    assert client.post(f"{API}/change-password", headers=op,
                       json={"current_password": "OperPass1234", "new_password": "BrandNew12345"}).status_code == 200
    assert _login("ah_op", "BrandNew12345").status_code == 200
    admin = _h("ah_admin", "AdminPass123")
    me = client.get(f"{API}/me", headers=admin).json()
    assert client.patch(f"{API}/users/{me['id']}", headers=admin, json={"is_active": False}).status_code == 400


def test_refresh_issues_a_working_new_token_and_rejects_expired():
    from datetime import timedelta
    from backend.auth.auth import create_access_token
    old = _login("ah_op", "OperPass1234").json()["access_token"]
    r = client.post(f"{API}/refresh", headers={"Authorization": f"Bearer {old}"})
    assert r.status_code == 200
    assert client.get(f"{API}/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200
    db = SessionLocal()
    uid = db.query(User).filter(User.username == "ah_op").first().id
    db.close()
    expired = create_access_token({"user_id": uid, "role": "operator"}, timedelta(seconds=-5))
    assert client.post(f"{API}/refresh", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
