"""Optional Redis for multi-node HA — graceful fallback to in-process when absent."""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_client = None
_checked = False


def get_redis():
    """Return a redis client or None if REDIS_URL is unset / unreachable."""
    global _client, _checked
    if _checked:
        return _client
    _checked = True
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return None
    try:
        import redis
        client = redis.from_url(url, socket_connect_timeout=1.5, decode_responses=True)
        client.ping()
        _client = client
        logger.info("Redis connected (%s)", url.split("@")[-1])
    except Exception as e:
        logger.warning("Redis unavailable — using in-process state: %s", e)
        _client = None
    return _client


def redis_health() -> dict:
    client = get_redis()
    if not client:
        return {"enabled": bool(os.getenv("REDIS_URL")), "connected": False, "mode": "in-process"}
    try:
        client.ping()
        return {"enabled": True, "connected": True, "mode": "redis"}
    except Exception as e:
        return {"enabled": True, "connected": False, "mode": "in-process", "error": str(e)}


def camera_offline_sla(last_seen_iso: Optional[str], sla_seconds: int = 30) -> str:
    """Return 'ok' | 'degraded' | 'offline' based on heartbeat age."""
    if not last_seen_iso:
        return "offline"
    from datetime import datetime
    try:
        ts = datetime.fromisoformat(last_seen_iso.replace("Z", "+00:00").replace("+00:00", ""))
        age = (datetime.utcnow() - ts).total_seconds()
    except Exception:
        return "offline"
    if age <= sla_seconds:
        return "ok"
    if age <= sla_seconds * 3:
        return "degraded"
    return "offline"
