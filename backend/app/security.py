from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable

from flask import Request


RateLimit = tuple[int, int]

# In-memory sliding windows are enough for the current single-process app.
# A multi-instance deployment should move these buckets into shared storage.
_RATE_LIMIT_WINDOWS: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    # Render and most reverse proxies pass the real client first in this header.
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.remote_addr or "unknown"


def _request_identifier(request: Request) -> str:
    # Auth endpoints are keyed by submitted account identifier as well as IP so
    # repeated attempts against one account are throttled consistently.
    if request.path in {
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/password-reset/request",
        "/api/auth/password-reset/confirm",
    }:
        payload = request.get_json(silent=True) or {}
        return (payload.get("username") or "").strip().lower()
    return ""


def _rate_limit_for(request: Request) -> RateLimit | None:
    if request.method == "OPTIONS" or not request.path.startswith("/api/"):
        return None

    # Account access and destructive profile actions get stricter limits than
    # ordinary writes because they are higher-risk abuse targets.
    if (
        request.path
        in {
            "/api/auth/login",
            "/api/auth/register",
            "/api/auth/password-reset/request",
            "/api/auth/password-reset/confirm",
        }
        and request.method == "POST"
    ):
        return 5, 5 * 60
    if request.path == "/api/auth/profile" and request.method == "DELETE":
        return 3, 5 * 60
    if request.method in {"POST", "PUT", "DELETE"}:
        return 30, 60
    # Realtime transit endpoints can refresh often, but still need a ceiling to
    # prevent one client from exhausting upstream feed/API capacity.
    if request.path in {"/api/arrivals", "/api/service-alerts"}:
        return 60, 60

    return None


def is_rate_limited(request: Request, now_factory: Callable[[], float] = time.time) -> bool:
    rate_limit = _rate_limit_for(request)
    if not rate_limit:
        return False

    limit, window_seconds = rate_limit
    now = now_factory()
    # Keep method/path/IP/account in the key so unrelated actions do not share a
    # bucket, while repeated attempts against the same surface do.
    key = ":".join(
        [
            request.method,
            request.path,
            _client_ip(request),
            _request_identifier(request),
        ]
    )
    bucket = _RATE_LIMIT_WINDOWS[key]

    # Drop expired hits before deciding whether the current request exceeds the
    # configured sliding window.
    while bucket and bucket[0] <= now - window_seconds:
        bucket.popleft()

    if len(bucket) >= limit:
        return True

    bucket.append(now)
    return False
