# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Mock interview generation.

Built from two real things: the person's actual experience and a specific
job's actual requirements — not a generic "top 50 interview questions"
list. Same credit system and cache as resume tailoring, so it costs
whatever the going rate for one AI generation is, not a separate meter.

Explicitly a REHEARSAL tool. It never claims to know what a real
interviewer will ask — the copy on every surface says "likely" and
"practice," and the model is told to say so in its own output too.
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from api.db import get_db
from api.auth import current_user
from api.access import require_seeker
from api.models import User, Position
from api.routers.ai import _call, _key, _cached, _store
from api import credits

# Rehearsing for your own interview is a seeker feature end to end — it is
# built from the signed-in person's own positions.
router = APIRouter(prefix="/api/interview", tags=["interview"],
                   dependencies=[Depends(require_seeker)])


class InterviewIn(BaseModel):
    job_title: str = Field(min_length=1)
    company: str = ""
    jd: str = ""             # optional — sharpens it a lot if given
    skills: list[str] = []   # what the posting asks for, if known


@router.post("/mock")
def generate_mock_interview(body: InterviewIn, user: User = Depends(current_user),
                            db: Session = Depends(get_db)):
    if user.plan == "free" and credits.remaining(db, user) <= 0:
        raise HTTPException(429, "No generations left this month. Refer a friend for +100, "
                                 "or upgrade — Pro includes far more.")

    positions = db.query(Position).filter(Position.user_id == user.id)\
                  .order_by(Position.started_on.desc()).all()
    if not positions:
        raise HTTPException(400, "Add at least one role to your profile first — "
                                 "questions are built from your actual experience.")

    exp_summary = "\n".join(
        f"- {p.role} at {p.company}: {'; '.join(p.bullets or [])[:400]}"
        for p in positions)
    total_months = sum(p.months for p in positions)
    y, mo = divmod(total_months, 12)
    total_label = (f"{y} yrs " if y else "") + (f"{mo} mos" if mo else "")

    jd_text = (body.jd or "").strip()[:2500]
    skills_text = ", ".join(body.skills) if body.skills else "not specified"

    key = _key("interview", user.id, body.job_title, body.company, jd_text, skills_text, total_months)
    result = _cached(db, key)
    if result is None:
        result = _call(f"""You are preparing a candidate for an interview. Build a mock interview
from their REAL experience below and the target role. This is a rehearsal
tool — be direct about what's likely to come up, never claim certainty
about what an actual interviewer will ask. Return ONLY minified JSON.

CANDIDATE EXPERIENCE — {total_label} total
{exp_summary}

TARGET ROLE: {body.job_title}{f' at {body.company}' if body.company else ''}
SKILLS/TOOLS THE POSTING ASKS FOR: {skills_text}
{f'JOB DESCRIPTION:{chr(10)}{jd_text}' if jd_text else 'No JD given — base this on the title and skills alone.'}

SCHEMA
{{"skills_tested":[{{"skill":"","why":""}}],
 "technical":[{{"question":"","what_they_want":"","answer_using_your_experience":"","watch_out_for":""}}],
 "behavioral":[{{"question":"","framework":"","answer_using_your_experience":""}}],
 "questions_to_ask_them":[""],
 "weak_spots":[""]}}

RULES
- skills_tested: 5-8 items, pulled from the JD/skills list, each with one
  line on why it likely matters for this specific role.
- technical: 5-7 questions, each answer draws on ONE OF THE CANDIDATE'S
  ACTUAL EXPERIENCES ABOVE — name the real company/project, don't invent one.
  If their experience genuinely doesn't cover something the role needs, say
  so in watch_out_for rather than fabricating an answer.
- behavioral: 4-5 questions (leadership, conflict, failure, ambiguity),
  each with a one-line framework (e.g. "STAR: situation, task, action,
  result") and a real-experience-grounded answer sketch.
- questions_to_ask_them: 4-5 genuinely useful ones specific to this role,
  not generic ("What's the culture like?").
- weak_spots: 2-4 honest gaps between their resume and this role's asks —
  the same kind of thing a tough interviewer would actually probe on.
- NEVER invent achievements, metrics, or outcomes not implied by their
  actual bullets. If unsure, phrase the answer as a framework rather than
  fabricated specifics.""", 1800, "mock interview")
        _store(db, key, result)
        if user.plan == "free":
            credits.spend(db, user)

    return result
