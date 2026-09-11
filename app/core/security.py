"""Rate limiting and API key protection utilities."""

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Header, HTTPException, Request, status

from app.core.config import get_settings

settings = get_settings()
_WINDOW_SECONDS = 60
_request_log: dict[str, deque] = defaultdict(deque)
_lock = Lock()


def _client_identifier(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host


def enforce_rate_limit(request: Request) -> None:
    identifier = _client_identifier(request)
    now = time.monotonic()
    with _lock:
        timestamps = _request_log[identifier]
        while timestamps and now - timestamps[0] > _WINDOW_SECONDS:
            timestamps.popleft()
        if len(timestamps) >= settings.rate_limit_per_minute:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded. Please retry later.")
        timestamps.append(now)


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not settings.is_production:
        return
    if not x_api_key or x_api_key != settings.app_secret_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key.")
