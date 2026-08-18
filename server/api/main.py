# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.settings import settings
from api.routers import jobs, profile, ai, billing, referrals, evaluation, support, interview

app = FastAPI(title="careerpilot.ai", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL] if settings.ENV != "dev" else ["*"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

for r in (jobs.router, profile.router, ai.router, billing.router, referrals.router, evaluation.router, support.router, interview.router):
    app.include_router(r)


@app.get("/health")
def health(): return {"ok": True, "env": settings.ENV}
