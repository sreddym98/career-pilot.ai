# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Main autopilot engine - orchestrates the full apply pipeline."""

import asyncio
import os
from typing import Dict, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from api.models import Job, User, Application, Position, UserSkill
from .tailor import TailorEngine
from .browser import BrowserAutomator


class AutopilotEngine:
    """Orchestrates automated job applications."""

    def __init__(self, db: Session, user: User, anthropic_key: Optional[str] = None):
        self.db = db
        self.user = user
        self.tailor = TailorEngine(api_key=anthropic_key)
        self.results = []

    def _user_profile(self) -> Dict:
        skills = [s.skill for s in self.db.query(UserSkill).filter(UserSkill.user_id == self.user.id).all()]
        positions = self.db.query(Position).filter(Position.user_id == self.user.id).order_by(Position.started_on.desc()).all()
        exp_lines = []
        for p in positions:
            bullets = "; ".join(p.bullets or [])
            exp_lines.append(f"{p.role} at {p.company} ({p.duration_label}): {bullets}")
        experience = "\n".join(exp_lines) or (self.user.summary or "")
        return {
            "name": self.user.name or "Candidate",
            "email": self.user.email,
            "phone": self.user.phone or "",
            "linkedin": self.user.linkedin or "",
            "location": self.user.location or "",
            "skills": skills,
            "experience": experience,
        }

    async def apply_to_jobs(self, jobs: List[Job],
                           auto_approve: bool = False,
                           max_per_run: int = 10) -> Dict:
        """
        Apply to a list of jobs automatically.

        Args:
            jobs: List of Job objects to apply to
            auto_approve: Skip manual review, auto-submit all
            max_per_run: Maximum applications per run

        Returns:
            {
                "total": int,
                "submitted": int,
                "failed": int,
                "needs_review": int,
                "results": [...]
            }
        """

        jobs_to_apply = []
        seen_companies = set()
        for job in jobs:
            company_key = (job.company or "").strip().casefold()
            if not company_key or company_key in seen_companies:
                self.results.append({
                    "job_id": job.fingerprint,
                    "job_title": job.title,
                    "company": job.company,
                    "success": False,
                    "status": "skipped_duplicate_company",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                continue
            existing = self.db.query(Application).filter(
                Application.user_id == self.user.id,
                Application.company.ilike(job.company),
                Application.status.in_(["submitted", "responded", "interview", "selected"])
            ).first()
            if existing:
                self.results.append({
                    "job_id": job.fingerprint,
                    "job_title": job.title,
                    "company": job.company,
                    "success": False,
                    "status": "skipped_company_already_applied",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                continue
            seen_companies.add(company_key)
            jobs_to_apply.append(job)
            if len(jobs_to_apply) >= max_per_run:
                break

        async with BrowserAutomator() as browser:
            for i, job in enumerate(jobs_to_apply):
                result = await self._apply_single_job(job, browser, auto_approve)
                self.results.append(result)

                # Save to database
                await self._save_application(job, result)

                # Delay between applications to avoid rate limiting
                if i < len(jobs_to_apply) - 1:
                    await asyncio.sleep(3)

        return self._summarize_results()

    async def _apply_single_job(self, job: Job, browser: BrowserAutomator,
                                auto_approve: bool) -> Dict:
        """Apply to a single job with full automation."""

        try:
            profile = self._user_profile()

            # 1. Tailor resume
            tailored_resume = await self._tailor_resume(job, profile)

            # 2. Generate cover letter
            cover_letter = await self._generate_cover_letter(job, profile)

            # 3. Fill and submit form
            user_data = {
                "name": profile["name"],
                "email": profile["email"],
                "phone": profile["phone"],
                "linkedin": profile["linkedin"],
                "location": profile["location"],
            }

            result = await browser.fill_and_submit(
                job.apply_url,
                user_data,
                resume_path=tailored_resume,
                cover_letter=cover_letter
            )

            return {
                "job_id": job.fingerprint,
                "job_title": job.title,
                "company": job.company,
                "url": job.apply_url,
                "timestamp": datetime.utcnow().isoformat(),
                **result
            }

        except Exception as e:
            return {
                "job_id": job.fingerprint,
                "job_title": job.title,
                "company": job.company,
                "success": False,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

    async def _tailor_resume(self, job: Job, profile: Dict) -> str:
        """Generate tailored resume and save to temp file."""

        tailored_text = self.tailor.tailor_resume(
            job.title,
            job.company,
            job.description or "",
            profile
        )

        # Save to temporary file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(tailored_text)
            return f.name

    async def _generate_cover_letter(self, job: Job, profile: Dict) -> str:
        """Generate personalized cover letter."""

        return self.tailor.generate_cover_letter(
            job.title,
            job.company,
            job.description or "",
            profile
        )

    async def _save_application(self, job: Job, result: Dict):
        """Save application record to database."""

        if result.get("success"):
            status = "submitted"
            note = "Submitted automatically by Full Autopilot"
        elif result.get("status") == "ready":
            status = "ready"
            note = "All fields filled and resume tailored — ready for final submit"
        elif result.get("status") == "needs_review":
            status = "needs_input"
            note = "Autofilled by Autopilot — needs your review before submit"
        elif result.get("status") == "closed":
            status = "closed"
            note = result.get("error") or "Job posting closed or filled by employer"
            # Deactivate job in DB so it stops appearing in active feeds
            job.active = False
            self.db.commit()
        else:
            status = "failed"
            note = f"Autopilot: {result.get('status', 'unknown')}"

        # Check if application already exists
        existing = self.db.query(Application).filter(
            Application.user_id == self.user.id,
            Application.fingerprint == job.fingerprint
        ).first()

        if existing:
            # Update existing record
            existing.status = status
            existing.note = note
            existing.blocker = result.get("error")
            self.db.commit()
        else:
            # Create new record
            app = Application(
                user_id=self.user.id,
                fingerprint=job.fingerprint,
                company=job.company,
                title=job.title,
                location=job.location,
                status=status,
                note=note,
                blocker=result.get("error")
            )
            self.db.add(app)
            self.db.commit()

    def _summarize_results(self) -> Dict:
        """Summarize all application results."""

        submitted = sum(1 for r in self.results if r.get("success"))
        skipped = sum(1 for r in self.results if r.get("status", "").startswith("skipped_"))
        failed = sum(1 for r in self.results if not r.get("success") and r.get("status") != "needs_review" and not r.get("status", "").startswith("skipped_"))
        needs_review = sum(1 for r in self.results if r.get("status") == "needs_review")

        return {
            "total": len(self.results),
            "submitted": submitted,
            "failed": failed,
            "skipped": skipped,
            "needs_review": needs_review,
            "success_rate": (submitted / len(self.results) * 100) if self.results else 0,
            "results": self.results
        }
