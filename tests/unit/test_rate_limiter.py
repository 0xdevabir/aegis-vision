"""Rate limiter: 429 (not 500) when exceeded; pipeline traffic with the internal key is exempt."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.middleware import rate_limiter as rl


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "k" * 32)
    monkeypatch.setattr(rl, "_limiter", rl.InMemoryRateLimiter())
    app = FastAPI()
    app.add_middleware(rl.RateLimitMiddleware)

    @app.post("/api/v1/alerts/dispatch")
    def dispatch():
        return {"ok": True}

    @app.post("/api/v1/auth/login")
    def login():
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


def test_exceeding_limit_returns_429_not_500(client):
    codes = [client.post("/api/v1/auth/login").status_code for _ in range(12)]
    assert codes[:10] == [200] * 10
    assert codes[10:] == [429, 429]
    assert client.post("/api/v1/auth/login").headers["retry-after"] == "60"


def test_valid_internal_key_is_exempt_but_wrong_key_is_not(client):
    good = {"X-Internal-Key": "k" * 32}
    assert all(client.post("/api/v1/alerts/dispatch", headers=good).status_code == 200 for _ in range(100))
    bad = {"X-Internal-Key": "wrong"}
    codes = [client.post("/api/v1/alerts/dispatch", headers=bad).status_code for _ in range(62)]
    assert codes[-1] == 429
