import hmac
import os
import time
import threading
from collections import defaultdict
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Dict


class InMemoryRateLimiter:
    def __init__(self):
        self._buckets: Dict[str, list] = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, key: str, max_requests: int, window_seconds: int) -> bool:
        now = time.time()
        with self._lock:
            if len(self._buckets) > 10_000:      # drop idle clients so the table cannot grow without bound
                for k in [k for k, b in self._buckets.items() if not b or b[-1] <= now - 3600]:
                    del self._buckets[k]
            bucket = self._buckets[key]
            cutoff = now - window_seconds
            bucket[:] = [t for t in bucket if t > cutoff]
            if len(bucket) >= max_requests:
                return False
            bucket.append(now)
            return True


_limiter = InMemoryRateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Strict limits on auth + internal event paths, a general limit on every other write."""

    _WRITE_LIMIT = 240          # per client per minute, all POST/PUT/PATCH/DELETE under /api/v1

    _PROTECTED = (
        "/api/v1/auth/login",
        "/api/v1/auth/users",
        "/api/v1/events/internal",
        "/api/v1/alerts/dispatch",
    )

    @staticmethod
    def _has_valid_internal_key(request: Request) -> bool:
        """The pipeline posts alerts at camera rate with the shared key; it is not a flood.

        A wrong or missing key is still throttled, so brute-forcing the key is limited.
        """
        expected = os.getenv("INTERNAL_API_KEY", "")
        got = request.headers.get("X-Internal-Key", "")
        return bool(expected) and bool(got) and hmac.compare_digest(got.encode(), expected.encode())

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        prefix = next((p for p in self._PROTECTED if path.startswith(p)), None)
        is_write = request.method in ("POST", "PUT", "PATCH", "DELETE") and path.startswith("/api/v1/")
        if prefix or is_write:
            if self._has_valid_internal_key(request):
                return await call_next(request)
            client_ip = request.client.host if request.client else "unknown"
            # Keyed on the matched prefix, not the full path: /auth/users/1, /2, ... share one budget.
            if prefix:
                key, limit = f"{client_ip}:{prefix}", 10 if "login" in prefix else 60
            else:
                key, limit = f"{client_ip}:write", self._WRITE_LIMIT
            if not _limiter.check(key, max_requests=limit, window_seconds=60):
                # Return (don't raise): exceptions in BaseHTTPMiddleware bypass FastAPI's
                # handlers and surface as a 500 with a stack trace.
                return JSONResponse(status_code=429, headers={"Retry-After": "60"},
                                    content={"detail": "Rate limit exceeded. Try again later."})
        return await call_next(request)
