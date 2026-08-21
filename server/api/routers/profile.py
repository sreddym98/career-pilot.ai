# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
import datetime as dt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from api.db import get_db
from api.auth import current_user, optional_user
from api.access import require_seeker
from api.models import User, Position, UserSkill, Connection

# Gated per-endpoint rather than on the router: /api/u/{slug} is a public page
# and must stay reachable with no session at all.
router = APIRouter(prefix="/api", tags=["profile"])

# Matches the options the profile form offers. Anything else is a client bug,
# and silently storing it would quietly break every visa filter downstream.
WORK_AUTH = {"usc", "gc", "h1b", "h4", "opt", "cpt", "l2", "tn", "e3"}
MAX_SKILLS = 60
# A slug is a path segment on our own domain — these would shadow real routes.
RESERVED_SLUGS = {"api", "u", "admin", "app", "www", "login", "signup", "join",
                  "settings", "billing", "support", "help", "about", "pricing",
                  "jobs", "bench", "dashboard", "me", "new", "static", "assets"}


class PositionIn(BaseModel):
    company: str
    role: str
    started_on: dt.date
    finished_on: dt.date | None = None
    location: str | None = None
    bullets: list[str] = []


class ProfileIn(BaseModel):
    """Every field optional — the profile page saves whichever card you edited,
    not the whole record, so an unsent field must mean "leave it alone" rather
    than "clear it"."""
    name: str | None = None
    headline: str | None = None
    location: str | None = None
    phone: str | None = None
    linkedin: str | None = None
    summary: str | None = None
    slug: str | None = None
    work_auth: list[str] | None = None


class SkillsIn(BaseModel):
    skills: list[str] = []
    top: list[str] = []          # the handful to lead with


def _total_months(ps): return sum(p.months for p in ps)
def _label(m):
    y, mo = divmod(m, 12)
    parts = []
    if y:  parts.append(f"{y} yr" + ("s" if y > 1 else ""))
    if mo: parts.append(f"{mo} mo" + ("s" if mo > 1 else ""))
    return " ".join(parts) or "0 mos"


@router.get("/profile")
def me(user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    ps = db.query(Position).filter(Position.user_id == user.id)\
           .order_by(Position.started_on.desc()).all()
    total = _total_months(ps)
    return {
        "id": user.id, "name": user.name, "email": user.email, "slug": user.slug,
        "headline": user.headline, "location": user.location, "summary": user.summary,
        "phone": user.phone, "linkedin": user.linkedin,
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
        "top_skills": [s.skill for s in db.query(UserSkill)
                       .filter(UserSkill.user_id == user.id, UserSkill.is_top == True)],
        "gaps": _gaps(ps),
    }


@router.put("/profile")
def update_profile(body: ProfileIn, user: User = Depends(require_seeker),
                   db: Session = Depends(get_db)):
    fields = body.model_dump(exclude_unset=True)

    # Validate everything BEFORE touching the row. Mutating first and checking
    # after leaves a half-applied object attached to the session when we raise,
    # and the next read in that same session sees the rejected value.
    slug = _MISSING
    if "slug" in fields:
        slug = _clean_slug(fields.pop("slug"))
        if slug and db.query(User).filter(User.slug == slug, User.id != user.id).first():
            raise HTTPException(409, "That profile address is already taken")

    auth = _MISSING
    if "work_auth" in fields:
        auth = fields.pop("work_auth") or []
        unknown = [a for a in auth if a not in WORK_AUTH]
        if unknown:
            raise HTTPException(400, f"Unknown work authorization: {', '.join(unknown)}")

    # "" is a real edit — it's how you clear a headline you no longer want —
    # but a nameless profile is not something the rest of the app can render.
    clean = {k: (v.strip() if isinstance(v, str) else v) for k, v in fields.items()}
    if "name" in clean and not clean["name"]:
        raise HTTPException(400, "Name can't be empty")

    if slug is not _MISSING: user.slug = slug
    if auth is not _MISSING: user.work_auth = auth
    for key, value in clean.items():
        setattr(user, key, value)

    db.commit(); db.refresh(user)
    return me(user, db)


# Distinguishes "field absent" from "field explicitly set to None".
_MISSING = object()


@router.put("/profile/skills")
def replace_skills(body: SkillsIn, user: User = Depends(require_seeker),
                   db: Session = Depends(get_db)):
    """Replaces the whole set. The skill editor is a tag field — the client
    knows the full list it wants, and diffing it here would only invent
    disagreements about what the user is looking at."""
    seen, cleaned = set(), []
    for s in body.skills:
        s = s.strip()
        if s and s.lower() not in seen:
            seen.add(s.lower()); cleaned.append(s)
    if len(cleaned) > MAX_SKILLS:
        raise HTTPException(400, f"That's more than {MAX_SKILLS} skills — trim it to the ones you'd defend in an interview")

    top = {t.strip().lower() for t in body.top}
    db.query(UserSkill).filter(UserSkill.user_id == user.id).delete()
    for s in cleaned:
        db.add(UserSkill(user_id=user.id, skill=s, is_top=s.lower() in top))
    db.commit()
    return {"skills": cleaned, "top": [s for s in cleaned if s.lower() in top]}


def _clean_slug(raw):
    """A slug becomes a public URL, so it gets normalised rather than trusted."""
    if raw is None: return None
    s = "".join(c if c.isalnum() else "-" for c in str(raw).strip().lower())
    s = "-".join(p for p in s.split("-") if p)[:40]
    if not s: return None
    if len(s) < 3: raise HTTPException(400, "Profile address needs at least 3 characters")
    if s in RESERVED_SLUGS: raise HTTPException(409, "That profile address is reserved")
    return s


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
def add_position(p: PositionIn, user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    _validate(p)
    row = Position(user_id=user.id, **p.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "duration_label": row.duration_label}


@router.put("/positions/{pid}")
def edit_position(pid: str, p: PositionIn, user: User = Depends(require_seeker),
                  db: Session = Depends(get_db)):
    _validate(p)
    row = db.query(Position).filter(Position.id == pid, Position.user_id == user.id).first()
    if not row: raise HTTPException(404, "Position not found")
    for k, v in p.model_dump().items(): setattr(row, k, v)
    db.commit()
    return {"id": row.id, "duration_label": row.duration_label}


@router.delete("/positions/{pid}")
def del_position(pid: str, user: User = Depends(require_seeker), db: Session = Depends(get_db)):
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
