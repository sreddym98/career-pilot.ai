# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
import json
import logging
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from api.settings import settings, production_problems
from api.routers import (jobs, profile, ai, billing, referrals, evaluation,
                         support, interview, integrations, accounts,
                         applications, connections, autopilot, bench, apply)
from api.db import init_db, engine
from api import models_events  # noqa: F401  registers processed_events on Base
from api.ratelimit import ai_limit

log = logging.getLogger("careerpilot")

app = FastAPI(title="careerpilot.ai", version="1.0",
              docs_url="/docs" if settings.ENV == "dev" else None,
              openapi_url="/openapi.json" if settings.ENV == "dev" else None,
              redoc_url=None)


def _security_headers() -> list[tuple[bytes, bytes]]:
    h = {"x-content-type-options": "nosniff",
         "referrer-policy": "strict-origin-when-cross-origin",
         "x-frame-options": "DENY",
         "permissions-policy": "camera=(), microphone=(), geolocation=()"}
    if settings.ENV != "dev":
        h["strict-transport-security"] = "max-age=31536000; includeSubDomains"
    return [(k.encode(), v.encode()) for k, v in h.items()]


class SecurityHeadersMiddleware:
    """Pure ASGI so the headers also land on responses produced by other
    middleware (413s, CORS preflights)."""
    def __init__(self, app): self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def _send(message):
            if message["type"] == "http.response.start":
                have = {k.lower() for k, _ in message.get("headers", [])}
                extra = [(k, v) for k, v in _security_headers() if k not in have]
                if scope["path"].startswith("/api/") and b"cache-control" not in have:
                    extra.append((b"cache-control", b"no-store"))
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)
        await self.app(scope, receive, _send)


class BodyLimitMiddleware:
    """Reject oversized request bodies, by Content-Length up front and by
    counting bytes for chunked uploads. The Stripe webhook gets a larger cap
    but is otherwise passed through untouched: signature verification needs
    the exact raw bytes."""
    def __init__(self, app): self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = (settings.MAX_WEBHOOK_BODY_BYTES
                 if scope["path"] == "/api/billing/webhook" else settings.MAX_BODY_BYTES)
        for k, v in scope["headers"]:
            if k == b"content-length":
                try:
                    if int(v) > limit:
                        return await self._reject(send)
                except ValueError:
                    return await self._reject(send, 400, "Bad Content-Length")
        seen = 0
        started = False
        rejected = False

        async def _receive():
            nonlocal seen, rejected
            if rejected:
                return {"type": "http.disconnect"}
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > limit and not started:
                    # Answer 413 ourselves, then tell the app the client left.
                    # Raising here would be swallowed by the framework's body
                    # parsing and surface as a misleading 400.
                    rejected = True
                    await self._reject(send)
                    return {"type": "http.disconnect"}
            return msg

        async def _send(message):
            nonlocal started
            if rejected:
                return
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        await self.app(scope, _receive, _send)

    @staticmethod
    async def _reject(send, status=413, msg="Request body too large"):
        body = json.dumps({"detail": msg}).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode()),
                                (b"connection", b"close")]})
        await send({"type": "http.response.body", "body": body})


# Order: last added is outermost. Headers wrap everything; CORS sits inside so
# preflights still get them; the body cap runs before any route reads a byte.
app.add_middleware(BodyLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL] if settings.ENV != "dev" else ["*"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    """Full traceback goes to the server log; the client gets nothing to work
    with. ServerErrorMiddleware sits outside our middleware, so the security
    headers are added here for 500s."""
    log.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    headers = {k.decode(): v.decode() for k, v in _security_headers()}
    return JSONResponse({"detail": "Internal server error"}, status_code=500, headers=headers)

for r in (accounts.router, jobs.router, profile.router, applications.router,
          connections.router, billing.router, referrals.router,
          evaluation.router, support.router, interview.router,
          integrations.router, autopilot.router, bench.router, apply.router):
    app.include_router(r)
# AI endpoints cost real money: bounded per user (and per IP) on top of credits.
app.include_router(ai.router, dependencies=[Depends(ai_limit)])


@app.on_event("startup")
def create_tables():
    problems = production_problems()
    if problems:
        raise RuntimeError("Refusing to start:\n  - " + "\n  - ".join(problems))
    init_db()
    if settings.ENV != "dev" and settings.AUTO_INGEST_ON_EMPTY:
        try:
            from api import ingest_job
            ingest_job.ensure_board_not_empty()
        except Exception:
            log.exception("could not start the first job import")


@app.get("/health")
def health():
    """Liveness only. Deliberately never touches the database, so uptime pings
    don't wake Neon."""
    return {"ok": True}


@app.get("/ready")
def ready():
    """Readiness: can we actually reach the database?"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        log.exception("readiness check failed")
        return JSONResponse({"ok": False}, status_code=503)
    return {"ok": True}
