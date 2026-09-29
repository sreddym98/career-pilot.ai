# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""The on-site Apply page, and what the browser extension reads.

NOTHING here submits an application. There is no server-side submission to
any employer, and the extension only fills fields: the user clicks the
employer's own Submit button. `applied` is recorded only when the user says so
(the web app's "Did you apply?" prompt, or the "I submitted it" button the user
presses in the extension overlay).
"""
import datetime as dt
import hashlib
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api import ats, credits, resume as R
from api.access import require_seeker
from api.auth import extension_or_user
from api.db import get_db
from api.models import Application, ExtensionToken, Job, Position, User, UserSkill
from api.ratelimit import ai_limit
from api import tokens

router = APIRouter(tags=["apply"])

MAX_ANSWER = 5000
MAX_ACTIVE_EXT_TOKENS = 5


def _seeker(user: User):
    if user.account_type != "seeker":
        raise HTTPException(403, "This is a seeker feature.")
    return user


def _facts(db: Session, user: User):
    positions = db.query(Position).filter(Position.user_id == user.id).all()
    skills = [s.skill for s in db.query(UserSkill).filter(UserSkill.user_id == user.id)]
    return positions, skills


def _mine(db: Session, user: User, app_id: str) -> Application:
    a = db.query(Application).filter(Application.id == app_id, Application.user_id == user.id).first()
    if not a:
        raise HTTPException(404, "Application not found")
    return a


def _questions(db: Session, job: Job | None) -> dict:
    if job is None:
        return {"supported": False, "ats": None, "reason": "no_job"}
    return ats.questions_for(db, job)


def _ensure_answers(db: Session, user: User, a: Application, job: Job | None, positions) -> dict:
    """First open: fetch the employer's form (or the standard questions) and
    pre-fill from the profile. Later opens keep the user's edited answers."""
    meta = dict(a.form_fields or {})
    if a.answers:
        return meta.get("questions_meta") or {}
    q = _questions(db, job)
    qs = q.get("questions") if q.get("supported") else ats.standard_questions()
    answers = ats.prefill(qs, ats.profile_facts(user, positions), has_cover_letter=True)
    info = {"supported": bool(q.get("supported")), "ats": q.get("ats"), "partial": bool(q.get("partial")),
            "reason": q.get("reason")}
    meta["questions_meta"] = info
    a.form_fields = meta
    a.answers = answers
    db.commit()
    return info


def _resume_of(a: Application) -> dict | None:
    return (a.tailored_resume or {}).get("resume")


def _view(db: Session, user: User, a: Application) -> dict:
    job = db.get(Job, a.fingerprint) if a.fingerprint else None
    positions, skills = _facts(db, user)
    info = _ensure_answers(db, user, a, job, positions)
    if not _resume_of(a) and job is not None:
        tr = dict(a.tailored_resume or {})
        tr["resume"] = R.base_resume(user, positions, skills, job)
        a.tailored_resume = tr
    if not a.cover_letter and job is not None:
        a.cover_letter = R.plain_cover_letter(user, positions, job)
    db.commit()
    answers = a.answers or []
    return {
        "application": {"id": a.id, "status": a.status, "origin": a.origin or "manual",
                        "company": a.company, "title": a.title, "location": a.location},
        "job": ({"fingerprint": job.fingerprint, "company": job.company, "title": job.title,
                 "location": job.location, "work_mode": job.work_mode, "employment": job.employment,
                 "apply_url": job.apply_url if (job.apply_url or "").lower().startswith(("https://", "http://")) else None,
                 "active": bool(job.active), "description": text_description(job.description)}
                if job else None),
        "questions": info,
        "answers": answers,
        "checklist": ats.checklist(answers),
        "resume": _resume_of(a),
        "cover_letter": a.cover_letter or "",
        "resume_cost": _resume_cost(db, user, a),
        "credits_remaining": credits.remaining(db, user),
    }


def text_description(desc: str | None) -> str:
    from api.routers.jobs import description_text
    return description_text(desc)


# ── start / read / save ─────────────────────────────────────────────────

class StartIn(BaseModel):
    fingerprint: str | None = Field(default=None, max_length=200)
    application_id: str | None = Field(default=None, max_length=64)


@router.post("/api/apply/start")
def start(body: StartIn, user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    """Open the Apply page for a job (creates the tracker row as 'opened' if
    there isn't one) or for an existing application (an Autopilot item)."""
    if body.application_id:
        return _view(db, user, _mine(db, user, body.application_id))
    fp = (body.fingerprint or "").strip()
    job = db.get(Job, fp) if fp else None
    if not job:
        raise HTTPException(404, "That job isn't on the board any more.")
    a = db.query(Application).filter(Application.user_id == user.id, Application.fingerprint == fp).first()
    if a is None:
        a = Application(user_id=user.id, fingerprint=fp, company=job.company, title=job.title,
                        location=job.location, status="opened", origin="manual")
        db.add(a); db.commit(); db.refresh(a)
    return _view(db, user, a)


@router.get("/api/apply/{app_id}")
def read(app_id: str, user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    return _view(db, user, _mine(db, user, app_id))


class SaveIn(BaseModel):
    answers: dict[str, str] | None = None        # question id -> value
    cover_letter: str | None = Field(default=None, max_length=8000)


@router.put("/api/apply/{app_id}")
def save(app_id: str, body: SaveIn, user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    a = _mine(db, user, app_id)
    if body.answers is not None:
        cur = [dict(x) for x in (a.answers or [])]
        by_id = {x.get("id"): x for x in cur}
        for qid, val in body.answers.items():
            q = by_id.get(qid)
            if q is None:
                continue                              # only the questions we showed
            v = str(val or "")[:MAX_ANSWER]
            if q.get("type") in ("select", "boolean") and v and q.get("options") and v not in q["options"]:
                raise HTTPException(400, f"'{v}' isn't one of the choices for: {q.get('label')}")
            if q.get("type") == "file" and q.get("source") == "file":
                continue                              # files come from us, not free text
            if v != (q.get("value") or ""):
                q["value"], q["source"], q["needs_you"] = v, ("you" if v else ""), not v
        a.answers = cur
    if body.cover_letter is not None:
        a.cover_letter = body.cover_letter.strip()[:8000]
    db.commit()
    return {"saved": True, "checklist": ats.checklist(a.answers or [])}


# ── tailored resume ─────────────────────────────────────────────────────

def _resume_cost(db: Session, user: User, a: Application) -> int:
    """0 when this job's Autopilot preparation already paid for it."""
    if (a.origin == "autopilot") and not (a.form_fields or {}).get("ai_resume_done"):
        return 0
    return 1


@router.post("/api/apply/{app_id}/resume", dependencies=[Depends(ai_limit)])
def tailor(app_id: str, user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    from api.routers import ai
    a = _mine(db, user, app_id)
    job = db.get(Job, a.fingerprint) if a.fingerprint else None
    if job is None:
        raise HTTPException(404, "This posting isn't on the board any more, so it can't be tailored to.")
    positions, skills = _facts(db, user)
    if not positions:
        raise HTTPException(400, "Add at least one role to your profile first.")
    cost = _resume_cost(db, user, a)
    phash = hashlib.sha256(json.dumps(
        [user.name, user.headline, user.summary, skills,
         [(p.id, p.company, p.role, str(p.started_on), str(p.finished_on), p.bullets) for p in positions]],
        sort_keys=True, default=str).encode()).hexdigest()[:16]
    key = ai._key("apply-resume", user.id, job.fingerprint, phash)
    got = ai._cached(db, key)
    cached = got is not None
    if not cached:
        if cost and credits.remaining(db, user) < 1:
            raise HTTPException(402, "You're out of generations this month. Your resume ordered for this job "
                                     "(no AI) is still ready to download.")
        try:
            got = ai._call(R.prompt(user, positions, skills, job), 2200, "apply resume", fast=True)
        except HTTPException as e:
            raise HTTPException(503, f"The AI couldn't do this right now ({e.detail}). Nothing was charged. "
                                     "Your resume ordered for this job is still ready.")
    res, why = R.check_ai(got, user, positions, skills, job)
    if res is None:
        print(f"[apply] {user.email} / {job.company}: tailored resume rejected ({why})")
        raise HTTPException(422, "The AI's draft added something that isn't in your profile, so we threw it away. "
                                 "Nothing was charged. Your resume ordered for this job is still ready.")
    resume, letter = res
    if not cached:
        ai._store(db, key, got)
    tr = dict(a.tailored_resume or {})
    tr["resume"] = resume
    a.tailored_resume = tr
    if letter:
        a.cover_letter = letter
    ff = dict(a.form_fields or {}); ff["ai_resume_done"] = True
    a.form_fields = ff
    if cost and not cached:
        credits.spend(db, user, 1)            # commits the resume and the charge together
    else:
        db.commit()
    return _view(db, user, a)


@router.get("/api/apply/{app_id}/resume.pdf")
def resume_pdf(app_id: str, user: User = Depends(extension_or_user), db: Session = Depends(get_db)):
    _seeker(user)
    a = _mine(db, user, app_id)
    r = _resume_of(a)
    if not r:
        job = db.get(Job, a.fingerprint) if a.fingerprint else None
        if job is None:
            raise HTTPException(404, "No resume for this application yet")
        positions, skills = _facts(db, user)
        r = R.base_resume(user, positions, skills, job)
    pdf = R.render_pdf(user, r)
    name = "".join(c for c in (user.name or "resume") if c.isalnum() or c in " -_").strip().replace(" ", "_") or "resume"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}_Resume.pdf"',
                             "Cache-Control": "no-store"})


# ── extension ───────────────────────────────────────────────────────────

@router.post("/api/auth/extension-token")
def extension_token(user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    """A scoped key for the browser extension. It can read the apply packet,
    download the tailored resume and report fill/applied status; nothing else."""
    active = (db.query(ExtensionToken).filter(ExtensionToken.user_id == user.id, ExtensionToken.revoked_at.is_(None))
              .order_by(ExtensionToken.created_at.asc()).all())
    now = dt.datetime.now(dt.timezone.utc)
    for old in active[:max(0, len(active) - MAX_ACTIVE_EXT_TOKENS + 1)]:
        old.revoked_at = now
    jti = uuid.uuid4().hex
    db.add(ExtensionToken(jti=jti, user_id=user.id, created_at=now))
    db.commit()
    return {**tokens.issue_extension(user, jti), "scope": tokens.EXTENSION_SCOPE}


@router.delete("/api/auth/extension-token")
def revoke_extension_tokens(user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    now = dt.datetime.now(dt.timezone.utc)
    n = 0
    for t in db.query(ExtensionToken).filter(ExtensionToken.user_id == user.id, ExtensionToken.revoked_at.is_(None)):
        t.revoked_at = now; n += 1
    db.commit()
    return {"revoked": n}


def _profile_for_ext(db: Session, user: User) -> dict:
    positions, _ = _facts(db, user)
    f = ats.profile_facts(user, positions)
    return {"first_name": f["first_name"], "last_name": f["last_name"], "full_name": f["full_name"],
            "email": f["email"], "phone": f["phone"], "location": f["location"], "linkedin": f["linkedin"],
            "current_company": f["current_company"], "current_title": f["current_title"]}


@router.get("/api/apply-packet")
def apply_packet(application_id: str | None = Query(default=None, max_length=64),
                 user: User = Depends(extension_or_user), db: Session = Depends(get_db)):
    """What the extension fills a form with. Without application_id: the
    profile basics only (for forms opened outside the Apply page)."""
    _seeker(user)
    out = {"profile": _profile_for_ext(db, user)}
    if not application_id:
        return out
    a = _mine(db, user, application_id)
    job = db.get(Job, a.fingerprint) if a.fingerprint else None
    out.update({
        "application_id": a.id, "company": a.company, "title": a.title,
        "apply_url": job.apply_url if job else None,
        "answers": [{k: q.get(k) for k in ("id", "label", "type", "required", "options", "value", "eeo")}
                    for q in (a.answers or [])],
        "cover_letter": a.cover_letter or "",
        "files": {"resume_pdf": f"/api/apply/{a.id}/resume.pdf"},
    })
    return out


class ReportIn(BaseModel):
    status: str                     # filled | applied
    filled: int | None = Field(default=None, ge=0, le=500)
    needs_you: int | None = Field(default=None, ge=0, le=500)


@router.post("/api/apply/{app_id}/report")
def report(app_id: str, body: ReportIn, user: User = Depends(extension_or_user), db: Session = Depends(get_db)):
    """`filled`: the extension filled the form (nothing was submitted).
    `applied`: ONLY sent when the user pressed "I submitted it" themselves."""
    _seeker(user)
    a = _mine(db, user, app_id)
    now = dt.datetime.now(dt.timezone.utc)
    if body.status == "filled":
        ff = dict(a.form_fields or {})
        ff["filled_at"] = now.isoformat()
        ff["filled"], ff["needs_you"] = body.filled, body.needs_you
        a.form_fields = ff
        if a.status in ("ready", "queued", "preparing", "needs_input"):
            a.status = "opened"
        if not a.note or a.note.startswith(("Approved", "Opened")):
            a.note = "Form filled by the extension — waiting for you to submit"
    elif body.status == "applied":
        a.status, a.note = "submitted", "You submitted it on the employer's page"
        a.applied_at = a.applied_at or now
    else:
        raise HTTPException(400, "status must be filled or applied")
    db.commit()
    return {"id": a.id, "status": a.status}


@router.post("/api/apply/{app_id}/handoff")
def handoff(app_id: str, user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    """The user pressed "Send to employer": the posting opens in their browser.
    An Autopilot item leaves the approval queue as 'opened'. Nothing is sent."""
    a = _mine(db, user, app_id)
    job = db.get(Job, a.fingerprint) if a.fingerprint else None
    if job is None or not job.active or job.link_status == "dead":
        raise HTTPException(409, "This posting has closed, so there's nothing to open.")
    if a.status in ("ready", "queued", "preparing", "needs_input"):
        a.status = "opened"
        a.note = "Opened the employer's form from the Apply page"
    db.commit()
    return {"id": a.id, "status": a.status, "apply_url": job.apply_url}
