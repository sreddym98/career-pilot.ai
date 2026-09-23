# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Autopilot API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
import asyncio

from api.db import get_db
from api.auth import current_user
from api.models import User, Job
from api.settings import settings
from api.autopilot import AutopilotEngine

router = APIRouter(prefix="/api/autopilot", tags=["autopilot"])


class AutopilotRequest(BaseModel):
    job_ids: List[str]  # List of job fingerprints to apply to
    auto_approve: bool = False
    max_per_run: int = 10


class AutopilotResponse(BaseModel):
    total: int
    submitted: int
    failed: int
    needs_review: int
    success_rate: float
    results: List[dict]


@router.post("/run", response_model=AutopilotResponse)
async def run_autopilot(
    body: AutopilotRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(current_user),
    db: Session = Depends(get_db)
):
    """
    Run autopilot to apply to selected jobs automatically.

    - Fetches the jobs
    - Tailors resumes using AI
    - Generates cover letters using AI
    - Fills and submits forms automatically (no manual approval)
    - Returns results summary
    """

    # Autopilot supports Groq, Anthropic, or local Ollama. Do not keep the old
    # Anthropic-only gate here; it rejected valid Groq/Ollama configurations.
    provider_configured = bool(settings.GROQ_API_KEY or settings.ANTHROPIC_API_KEY)
    if not provider_configured:
        try:
            import requests
            requests.get("http://localhost:11434/api/tags", timeout=2).raise_for_status()
            provider_configured = True
        except Exception:
            provider_configured = False
    if not provider_configured:
        raise HTTPException(400, "No AI provider configured. Add GROQ_API_KEY or ANTHROPIC_API_KEY, or start Ollama with: ollama serve")

    # Fetch jobs
    jobs = db.query(Job).filter(Job.fingerprint.in_(body.job_ids)).all()
    if not jobs:
        raise HTTPException(404, "No jobs found with the provided IDs")

    # Initialize autopilot engine
    engine = AutopilotEngine(db, user)

    # Run in background so API doesn't timeout
    background_tasks.add_task(
        engine.apply_to_jobs,
        jobs,
        auto_approve=body.auto_approve,
        max_per_run=body.max_per_run
    )

    return {
        "total": len(jobs),
        "submitted": 0,
        "failed": 0,
        "needs_review": 0,
        "success_rate": 0,
        "results": [],
        "status": "running_in_background"
    }


@router.get("/status")
def autopilot_status(
    user: User = Depends(current_user),
    db: Session = Depends(get_db)
):
    """Get status of autopilot runs and applications."""

    from api.models import Application

    total_apps = db.query(Application).filter(Application.user_id == user.id).count()
    submitted = db.query(Application).filter(
        Application.user_id == user.id,
        Application.status == "submitted"
    ).count()
    failed = db.query(Application).filter(
        Application.user_id == user.id,
        Application.status == "failed"
    ).count()
    needs_review = db.query(Application).filter(
        Application.user_id == user.id,
        Application.status == "needs_input"
    ).count()

    return {
        "total_applications": total_apps,
        "submitted": submitted,
        "failed": failed,
        "needs_review": needs_review,
        "success_rate": (submitted / total_apps * 100) if total_apps else 0
    }


@router.get("/ready-jobs")
def get_ready_jobs(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    limit: int = 20
):
    """
    Get list of jobs ready for autopilot.

    Filters:
    - Active jobs
    - Matching user's role families
    - Not already applied to
    - Have apply_url
    """

    from api.models import Application

    # Get already applied job IDs
    applied_ids = db.query(Application.fingerprint).filter(
        Application.user_id == user.id
    ).all()
    applied_ids = set(f[0] for f in applied_ids if f[0])

    # Get jobs matching user profile
    jobs = db.query(Job).filter(
        Job.active == True,
        Job.apply_url.isnot(None),
        Job.role_family.in_(user.role_families) if user.role_families else True
    ).limit(limit).all()

    return {
        "ready_jobs": [
            {
                "fingerprint": j.fingerprint,
                "company": j.company,
                "title": j.title,
                "location": j.location,
                "employment": j.employment,
                "already_applied": j.fingerprint in applied_ids
            }
            for j in jobs
        ]
    }
