# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.settings import settings
from api.routers import (jobs, profile, ai, billing, referrals, evaluation,
                         support, interview, integrations, accounts,
                         applications, connections)
from api.db import init_db

app = FastAPI(title="careerpilot.ai", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL] if settings.ENV != "dev" else ["*"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

for r in (accounts.router, jobs.router, profile.router, applications.router,
          connections.router, ai.router, billing.router, referrals.router,
          evaluation.router, support.router, interview.router,
          integrations.router):
    app.include_router(r)


@app.on_event("startup")
def create_tables():
    init_db()


@app.get("/health")
def health(): return {"ok": True, "env": settings.ENV}
