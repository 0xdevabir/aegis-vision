"""POST with retries and a real success check (a 5xx or timeout is a failure, not a delivery)."""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)


def sign(body: bytes, secret: str, timestamp: str) -> str:
    """HMAC-SHA256 over "<timestamp>.<body>": the receiver can check origin, integrity and freshness."""
    return "sha256=" + hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


async def post_with_retry(client: httpx.AsyncClient, url: str, payload: dict, *, attempts: int = 3,
                          timeout: float = 5.0, backoff: float = 0.5) -> bool:
    secret = os.getenv("WEBHOOK_SIGNING_SECRET", "")
    for i in range(attempts):
        try:
            if secret:
                # Sign the exact bytes sent; a fresh timestamp per attempt keeps retries inside
                # the receiver's replay window.
                body = json.dumps(payload, default=str, separators=(",", ":")).encode()
                ts = str(int(time.time()))
                resp = await client.post(url, content=body, timeout=timeout, headers={
                    "Content-Type": "application/json", "X-Aegis-Timestamp": ts,
                    "X-Aegis-Signature": sign(body, secret, ts)})
            else:
                resp = await client.post(url, json=payload, timeout=timeout)
            if resp.status_code < 400:
                return True
            logger.warning(f"POST {url} -> HTTP {resp.status_code} (attempt {i + 1}/{attempts})")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"POST {url} failed: {e} (attempt {i + 1}/{attempts})")
        if i < attempts - 1:
            await asyncio.sleep(backoff * (2 ** i))
    return False
