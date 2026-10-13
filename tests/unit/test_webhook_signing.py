"""Outbound webhooks carry an HMAC signature when WEBHOOK_SIGNING_SECRET is set."""
import asyncio
import hashlib
import hmac
from types import SimpleNamespace

from backend.utils import http_retry


class _Client:
    def __init__(self):
        self.calls = []

    async def post(self, url, **kw):
        self.calls.append(kw)
        return SimpleNamespace(status_code=200)


def _post(payload):
    client = _Client()
    assert asyncio.new_event_loop().run_until_complete(http_retry.post_with_retry(client, "http://x", payload))
    return client.calls[0]


def test_signature_verifies_against_the_bytes_sent(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SIGNING_SECRET", "s3cret")
    call = _post({"alert_type": "weapon", "n": 1})
    ts, sig = call["headers"]["X-Aegis-Timestamp"], call["headers"]["X-Aegis-Signature"]
    expected = hmac.new(b"s3cret", ts.encode() + b"." + call["content"], hashlib.sha256).hexdigest()
    assert sig == "sha256=" + expected
    assert http_retry.sign(call["content"] + b" ", "s3cret", ts) != sig      # any change breaks it


def test_unsigned_when_no_secret(monkeypatch):
    monkeypatch.delenv("WEBHOOK_SIGNING_SECRET", raising=False)
    assert _post({"a": 1}) == {"json": {"a": 1}, "timeout": 5.0}
