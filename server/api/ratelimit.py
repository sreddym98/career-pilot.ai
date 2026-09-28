# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""In-process sliding-window rate limiter.

One Render instance, no Redis: state lives in this process and resets on
restart. That is acceptable for abuse control (brute force, SMS pumping, AI
cost) and not a substitute for edge rate limiting if the service ever scales
out horizontally.
"""
import hashlib
import ipaddress
import math
import threading
import time
from collections import deque

from fastapi import Header, HTTPException, Request

from api.settings import settings

_now = time.monotonic          # tests may replace this
_lock = threading.Lock()
_hits: dict[str, deque] = {}
_MAX_KEYS = 20000


def reset() -> None:
    """Forget all state (tests)."""
    with _lock:
        _hits.clear()


def _prune(now: float) -> None:
    # Called with the lock held, only when the table is large.
    for k in [k for k, d in _hits.items() if not d or d[-1] < now - 86400]:
        _hits.pop(k, None)


def hit(checks: list[tuple[str, int, int]]) -> int:
    """Record one hit against every (key, limit, window_s) atomically.

    Returns 0 when allowed. When any key is over its limit, records nothing and
    returns the seconds to wait (>= 1)."""
    now = _now()
    with _lock:
        if len(_hits) > _MAX_KEYS:
            _prune(now)
        wait = 0
        for key, limit, window in checks:
            d = _hits.get(key)
            if d is None:
                continue
            while d and d[0] <= now - window:
                d.popleft()
            if len(d) >= limit:
                wait = max(wait, math.ceil(d[0] + window - now))
        if wait:
            return max(wait, 1)
        for key, limit, window in checks:
            _hits.setdefault(key, deque(maxlen=max(limit, 1))).append(now)
        return 0


def client_ip(request: Request) -> str:
    """Best-effort client address.

    In dev the socket peer is used and X-Forwarded-For is ignored. Elsewhere the
    app sits behind Render's proxy, so the socket peer is the proxy and the real
    client comes from X-Forwarded-For, picked by TRUSTED_IP_HOP. Anything that
    isn't a valid IP falls back to the peer, so a garbage header can't mint
    unlimited fresh buckets. A client can still prepend fake hops; per-email and
    global auth ceilings exist so that never becomes a way around them.
    """
    peer = request.client.host if request.client else "unknown"
    if settings.ENV == "dev":
        return peer
    xff = request.headers.get("x-forwarded-for", "")
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    if not parts:
        return peer
    try:
        cand = parts[settings.TRUSTED_IP_HOP]
    except IndexError:
        return peer
    try:
        return str(ipaddress.ip_address(cand))
    except ValueError:
        return peer


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def _too_many(wait: int):
    raise HTTPException(429, f"Too many requests. Try again in {wait} seconds.",
                        headers={"Retry-After": str(wait)})


def _enforce(checks):
    if not settings.RATE_LIMIT_ENABLED:
        return
    wait = hit(checks)
    if wait:
        _too_many(wait)


def user_key(request: Request, authorization: str | None) -> str:
    """Stable identity for per-user limits: the verified email claim, else a
    hash of the bearer token, else (dev, no credential) the client IP."""
    if authorization and authorization.lower().startswith("bearer "):
        tok = authorization[7:].strip()
        if tok:
            from api import tokens
            claims = tokens.verify(tok)
            if claims and claims.get("email"):
                return "u:" + _h(str(claims["email"]).lower())
            return "t:" + _h(tok)
    return "ip:" + client_ip(request)


async def auth_limit(request: Request):
    """Dependency for sign-in / sign-up."""
    email = ""
    try:
        data = await request.json()
        email = str(data.get("email", "")).strip().lower()[:254]
    except Exception:
        pass
    ip = client_ip(request)
    w = settings.RATE_AUTH_WINDOW_S
    checks = [(f"auth:ip:{ip}", settings.RATE_AUTH_PER_IP, w),
              ("auth:global", settings.RATE_AUTH_GLOBAL, w)]
    if email:
        checks += [(f"auth:ipe:{ip}:{_h(email)}", settings.RATE_AUTH_PER_IP_EMAIL, w),
                   (f"auth:e:{_h(email)}", settings.RATE_AUTH_PER_EMAIL, w)]
    _enforce(checks)


def per_user(name: str, limit_attr: str, window_attr: str):
    """Dependency factory: `limit_attr` hits per `window_attr` seconds per user."""
    def dep(request: Request, authorization: str = Header(None)):
        _enforce([(f"{name}:{user_key(request, authorization)}",
                   getattr(settings, limit_attr), getattr(settings, window_attr))])
    return dep


def ai_limit(request: Request, authorization: str = Header(None)):
    w = settings.RATE_AI_WINDOW_S
    _enforce([(f"ai:{user_key(request, authorization)}", settings.RATE_AI_PER_USER, w),
              (f"aiip:{client_ip(request)}", settings.RATE_AI_PER_IP, w)])
