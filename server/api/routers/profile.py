# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
import datetime as dt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from api.db import get_db
from api.auth import current_user, optional_user
from api.models import User, Position, UserSkill, Connection

router = APIRouter(prefix="/api", tags=["profile"])


class PositionIn(BaseModel):
    company: str
    role: str
    started_on: dt.date
    finished_on: dt.date | None = None
    location: str | None = None
    bullets: list[str] = []


def _total_months(ps): return sum(p.months for p in ps)
def _label(m):
    y, mo = divmod(m, 12)
    parts = []
    if y:  parts.append(f"{y} yr" + ("s" if y > 1 else ""))
    if mo: parts.append(f"{mo} mo" + ("s" if mo > 1 else ""))
    return " ".join(parts) or "0 mos"


@router.get("/profile")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ps = db.query(Position).filter(Position.user_id == user.id)\
           .order_by(Position.started_on.desc()).all()
    total = _total_months(ps)
    return {
        "id": user.id, "name": user.name, "email": user.email, "slug": user.slug,
        "headline": user.headline, "location": user.location, "summary": user.summary,
        "work_auth": user.work_auth or [], "plan": user.plan,
        "referral_code": user.referral_code,
        "total_months": total, "total_label": _label(total),
        "positions": [{
            "id": p.id, "company": p.company, "role": p.role,
            "started_on": p.started_on, "finished_on": p.finished_on,
            "location": p.location, "bullets": p.bullets or [],
            "months": p.months, "duration_label": p.duration_label,
        } for p in ps],
        "skills": [s.skill for s in db.query(UserSkill).filter(UserSkill.user_id == user.id)],
        "gaps": _gaps(ps),
    }


def _gaps(ps):
    """Surface employment gaps on the user's own profile — better they
    see it here than get surprised in a screening call."""
    out = []
    ordered = sorted(ps, key=lambda p: p.started_on)
    for a, b in zip(ordered, ordered[1:]):
        end = a.finished_on
        if not end: continue
        m = (b.started_on.year - end.year) * 12 + (b.started_on.month - end.month) - 1
        if m >= 2:
            out.append({"from": f"{end:%b %Y}", "to": f"{b.started_on:%b %Y}",
                        "months": m, "label": _label(m)})
    return out


@router.post("/positions")
def add_position(p: PositionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _validate(p)
    row = Position(user_id=user.id, **p.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "duration_label": row.duration_label}


@router.put("/positions/{pid}")
def edit_position(pid: str, p: PositionIn, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    _validate(p)
    row = db.query(Position).filter(Position.id == pid, Position.user_id == user.id).first()
    if not row: raise HTTPException(404, "Position not found")
    for k, v in p.model_dump().items(): setattr(row, k, v)
    db.commit()
    return {"id": row.id, "duration_label": row.duration_label}


@router.delete("/positions/{pid}")
def del_position(pid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = db.query(Position).filter(Position.user_id == user.id).count()
    if n <= 1: raise HTTPException(400, "Keep at least one role on your profile")
    row = db.query(Position).filter(Position.id == pid, Position.user_id == user.id).first()
    if not row: raise HTTPException(404, "Position not found")
    db.delete(row); db.commit()
    return {"deleted": True}


def _validate(p: PositionIn):
    if not p.company.strip(): raise HTTPException(400, "Company is required")
    if not p.role.strip():    raise HTTPException(400, "Job title is required")
    if p.started_on > dt.date.today(): raise HTTPException(400, "Start date is in the future")
    if p.finished_on and p.finished_on < p.started_on:
        raise HTTPException(400, "End date is before the start date")
    if not p.bullets: raise HTTPException(400, "Add at least one bullet point")


@router.get("/u/{slug}")
def public_profile(slug: str, db: Session = Depends(get_db)):
    """Public page — no auth. Only fields the user chose to publish."""
    user = db.query(User).filter(User.slug == slug).first()
    if not user: raise HTTPException(404, "Profile not found")
    ps = db.query(Position).filter(Position.user_id == user.id)\
           .order_by(Position.started_on.desc()).all()
    return {"name": user.name, "headline": user.headline, "location": user.location,
            "summary": user.summary, "total_label": _label(_total_months(ps)),
            "positions": [{"company": p.company, "role": p.role,
                           "dates": f"{p.started_on:%b %Y} – " + (f"{p.finished_on:%b %Y}" if p.finished_on else "Present"),
                           "duration": p.duration_label, "bullets": p.bullets} for p in ps]}
