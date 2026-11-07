import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import AppError

_hits: dict[str, deque] = defaultdict(deque)


def reset() -> None:
    _hits.clear()


def client_ip(request: Request) -> str:
    """Behind the Next.js /api proxy every request comes from the proxy, so the client address must come from
    X-Forwarded-For. That header is only trusted when TRUST_PROXY_HEADERS=true (it is trivially spoofable otherwise)."""
    if get_settings().trust_proxy_headers:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd.strip():
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "x"


def limit(name: str, per_minute: int):
    """Dependency factory: in-memory sliding window per client IP (single-instance deployments)."""

    def dep(request: Request):
        if not get_settings().rate_limit_enabled:
            return
        key = f"{name}:{client_ip(request)}"
        now = time.monotonic()
        q = _hits[key]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= per_minute:
            raise AppError(429, "rate_limited", "Too many requests, please slow down")
        q.append(now)

    return dep
