# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.settings import settings, production_problems
from api.routers import (jobs, profile, ai, billing, referrals, evaluation,
                         support, interview, integrations, accounts,
                         applications, connections, autopilot)
from api.db import init_db

app = FastAPI(title="careerpilot.ai", version="1.0",
              docs_url="/docs" if settings.ENV == "dev" else None,
              redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL] if settings.ENV != "dev" else ["*"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

for r in (accounts.router, jobs.router, profile.router, applications.router,
          connections.router, ai.router, billing.router, referrals.router,
          evaluation.router, support.router, interview.router,
          integrations.router, autopilot.router):
    app.include_router(r)


@app.on_event("startup")
def create_tables():
    problems = production_problems()
    if problems:
        raise RuntimeError("Refusing to start:\n  - " + "\n  - ".join(problems))
    init_db()


@app.get("/health")
def health(): return {"ok": True, "env": settings.ENV}
