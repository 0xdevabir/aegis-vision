"""POST with retries and a real success check (a 5xx or timeout is a failure, not a delivery)."""
import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


async def post_with_retry(client: httpx.AsyncClient, url: str, payload: dict, *, attempts: int = 3,
                          timeout: float = 5.0, backoff: float = 0.5) -> bool:
    for i in range(attempts):
        try:
            resp = await client.post(url, json=payload, timeout=timeout)
            if resp.status_code < 400:
                return True
            logger.warning(f"POST {url} -> HTTP {resp.status_code} (attempt {i + 1}/{attempts})")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"POST {url} failed: {e} (attempt {i + 1}/{attempts})")
        if i < attempts - 1:
            await asyncio.sleep(backoff * (2 ** i))
    return False
