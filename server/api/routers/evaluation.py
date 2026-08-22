# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Paid profile evaluation — $5, one-time.

Analyses resume/experience, career goals, and visa status together, because
a strong resume with the wrong visa story or no clear target undersells
someone just as much as weak bullets do.

The report is generated once, on the first successful GET after payment, and
cached on the Evaluation row — regenerating the same $5 report for the same
person costs nothing on repeat views.
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from api.db import get_db
from api.auth import current_user
from api.access import require_seeker
from api.models import User, Position, Evaluation
from api.routers.ai import _call, _key, _cached, _store

# Evaluates one person's own resume, goals and visa story — seeker only.
router = APIRouter(prefix="/api/evaluation", tags=["evaluation"],
                   dependencies=[Depends(require_seeker)])


class GoalsIn(BaseModel):
    target_title: str = ""
    target_industries: list[str] = []
    timeline: str = ""          # "immediately" | "1-3 months" | "exploring"
    relocation: str = ""        # "open" | "remote only" | "specific city"
    priorities: list[str] = []  # e.g. ["salary","stability","visa sponsorship","growth"]
    notes: str = ""


@router.get("/{eval_id}")
def get_evaluation(eval_id: str, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    ev = db.query(Evaluation).filter(Evaluation.id == eval_id, Evaluation.user_id == user.id).first()
    if not ev:
        raise HTTPException(404, "Evaluation not found")
    return {"id": ev.id, "paid": ev.paid, "report": ev.report,
            "created_at": ev.created_at, "paid_at": ev.paid_at}


@router.post("/{eval_id}/goals")
def set_goals(eval_id: str, goals: GoalsIn, user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    """Career goals are collected before payment, so the checkout page
    already knows what it's evaluating against."""
    ev = db.query(Evaluation).filter(Evaluation.id == eval_id, Evaluation.user_id == user.id).first()
    if not ev:
        raise HTTPException(404, "Evaluation not found")
    ev.report = {"_goals": goals.model_dump()}
    db.commit()
    return {"saved": True}


@router.post("/{eval_id}/run")
def run_evaluation(eval_id: str, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    ev = db.query(Evaluation).filter(Evaluation.id == eval_id, Evaluation.user_id == user.id).first()
    if not ev:
        raise HTTPException(404, "Evaluation not found")
    if not ev.paid:
        # Payment gate. Webhook flips `paid` — see billing.py. Without this
        # check anyone could call this endpoint for a free report.
        raise HTTPException(402, "This evaluation hasn't been paid for yet.")
    if ev.report and "summary" in ev.report:
        return ev.report  # already generated — no repeat AI cost

    goals = (ev.report or {}).get("_goals", {})
    positions = db.query(Position).filter(Position.user_id == user.id)\
                  .order_by(Position.started_on.desc()).all()
    if not positions:
        raise HTTPException(400, "Add at least one role to your profile before evaluating it")

    total_months = sum(p.months for p in positions)
    y, mo = divmod(total_months, 12)
    total_label = (f"{y} yrs " if y else "") + (f"{mo} mos" if mo else "")
    def _fmt_end(p):
        return f"{p.finished_on:%b %Y}" if p.finished_on else "Present"
    exp_summary = "\n".join(
        f"- {p.role} at {p.company} ({p.started_on:%b %Y}–{_fmt_end(p)}): "
        f"{'; '.join(p.bullets or [])[:400]}"
        for p in positions)

    work_auth = ", ".join(user.work_auth or []) or "not stated"
    goals_txt = (
        f"Target title: {goals.get('target_title','not specified')}\n"
        f"Target industries: {', '.join(goals.get('target_industries', [])) or 'not specified'}\n"
        f"Timeline: {goals.get('timeline','not specified')}\n"
        f"Relocation: {goals.get('relocation','not specified')}\n"
        f"Priorities: {', '.join(goals.get('priorities', [])) or 'not specified'}\n"
        f"Notes from candidate: {goals.get('notes','') or 'none'}"
    )

    key = _key("eval", user.id, total_months, json.dumps(goals, sort_keys=True), work_auth)
    report = _cached(db, key)
    if report is None:
        report = _call(f"""You are evaluating a job seeker's profile for readiness — not writing
their resume. Be direct and specific. Return ONLY minified JSON.

EXPERIENCE — {total_label} total
{exp_summary}

WORK AUTHORIZATION: {work_auth}

CAREER GOALS
{goals_txt}

SCHEMA
{{"readiness_score":0,
 "headline":"",
 "experience_review":{{"strengths":[""],"gaps":[""],"seniority_match":""}},
 "visa_assessment":{{"status":"","risk":"low|medium|high","note":""}},
 "goal_alignment":{{"realistic":true,"note":"","timeline_feedback":""}},
 "next_steps":[""],
 "red_flags":[""]}}

RULES
- readiness_score: 0-100. Be honest — a mediocre profile does not get 85.
- experience_review.seniority_match: does their actual experience match the
  seniority of the title they're targeting? Say plainly if it's a stretch.
- visa_assessment.risk: "high" if their status commonly limits which
  employers will even consider them (e.g. OPT nearing expiry with no H1B
  plan, or a status requiring sponsorship in a market that's tightened).
  "low" if USC/GC or a stable, well-understood status.
- goal_alignment.realistic: is the stated timeline realistic given the
  market and their profile? Don't just validate — say so if it's not.
- next_steps: 4-6 concrete actions, ordered by impact. Not generic advice —
  reference their actual gaps.
- red_flags: things that will concern a recruiter (unexplained gaps,
  mismatched seniority, visa timing risk). Empty array if genuinely none.
- Never invent experience, credentials, or outcomes not stated above.""",
            1400, "profile evaluation")
        _store(db, key, report)

    report["_goals"] = goals
    ev.report = report
    db.commit()
    return report
