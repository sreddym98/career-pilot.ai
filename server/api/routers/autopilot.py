# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Autopilot — scheduled job matching with one-tap batch approval.

What runs here is everything up to the send: at each of a user's slots the
server finds fresh matching roles, tailors a cover letter and highlights for
each, and parks them as `ready` applications. Nothing is ever sent unattended
(see decisions: unattended sending from a personal Gmail gets accounts flagged,
and an unchecked AI email is a mistake you can't take back). Approving marks the
application opened and hands back the posting to submit.

It runs on the server, on a schedule, so it works with the tab closed. Free
hosts sleep, so the schedule is driven from outside: a cron (GitHub Actions)
POSTs /api/autopilot/tick with the shared CRON_SECRET, which also wakes the
host. The tick answers immediately and does the work in the background.
"""
import datetime as dt
import hmac
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from api import credits, mailer
from api.access import require_seeker
from api.db import SessionLocal, get_db
from api.models import (Application, AutopilotConfig, AutopilotRun, Integration,
                        Job, Position, User, UserSkill)
from api.routers import ai
from api.settings import settings

router = APIRouter(prefix="/api/autopilot", tags=["autopilot"])

DAILY_CAP = {"pro": 60, "recruiter": 60}   # free has no Autopilot
MAX_PER_RUN = 5            # bounds AI spend and run time per slot
MAX_QUEUE = 25             # stop piling up work the user hasn't looked at
MAX_USERS_PER_TICK = 40    # one tick is one HTTP-triggered background job
FRESH_DAYS = 14
WORK_STYLES = ("", "remote", "hybrid", "onsite")


# ── config ───────────────────────────────────────────────────────────────

def _config(db: Session, user: User) -> AutopilotConfig:
    cfg = db.get(AutopilotConfig, user.id)
    if not cfg:
        cfg = AutopilotConfig(user_id=user.id, on=False, resume_confirmed=False,
                              slots=[9, 13, 17], titles=[], skills=[], work_style="")
        db.add(cfg); db.commit(); db.refresh(cfg)
    return cfg


def _gates(db: Session, user: User, cfg: AutopilotConfig) -> dict:
    rows = {r.provider: r for r in db.query(Integration).filter(Integration.user_id == user.id)}
    return {
        "gmailConnected": bool(rows.get("gmail") and rows["gmail"].status == "connected"),
        "phoneVerified": bool(rows.get("phone") and rows["phone"].status == "verified"),
        "resumeConfirmed": bool(cfg.resume_confirmed),
    }


def _cap(user: User) -> int:
    return DAILY_CAP.get(user.plan, 0)


def _item(a: Application, job: Job | None) -> dict:
    return {"id": a.id, "fingerprint": a.fingerprint, "company": a.company, "title": a.title, "location": a.location,
            "subject": (a.form_fields or {}).get("subject") or f"{a.title} — application",
            "apply_url": job.apply_url if job else None,
            "matched_at": a.updated_at}


def _queue(db: Session, user: User) -> list[Application]:
    return (db.query(Application)
            .filter(Application.user_id == user.id, Application.origin == "autopilot",
                    Application.status == "ready")
            .order_by(Application.updated_at.desc()).all())


def _state(db: Session, user: User) -> dict:
    cfg = _config(db, user)
    q = _queue(db, user)
    jobs = {j.fingerprint: j for j in db.query(Job).filter(
        Job.fingerprint.in_([a.fingerprint for a in q if a.fingerprint]))} if q else {}
    runs = (db.query(AutopilotRun).filter(AutopilotRun.user_id == user.id)
            .order_by(AutopilotRun.ran_at.desc()).limit(10).all())
    return {
        "on": bool(cfg.on), "slots": sorted(cfg.slots or []), "tz": cfg.tz,
        "titles": cfg.titles or [], "skills": cfg.skills or [],
        "workStyle": cfg.work_style or "", "dailyCap": _cap(user),
        "plan": user.plan, **_gates(db, user, cfg),
        "queue": [_item(a, jobs.get(a.fingerprint)) for a in q],
        "runs": [{"at": r.ran_at, "found": r.found, "prepared": r.prepared,
                  "skipped": r.skipped, "note": r.note} for r in runs],
        "credits_remaining": credits.remaining(db, user),
    }


class ConfigIn(BaseModel):
    on: bool | None = None
    slots: list[int] | None = None
    tz: str | None = None
    titles: list[str] | None = Field(default=None, max_length=10)
    skills: list[str] | None = Field(default=None, max_length=30)
    workStyle: str | None = None


@router.get("")
def get_state(user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    return _state(db, user)


@router.put("")
def save(body: ConfigIn, user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    cfg = _config(db, user)

    if body.slots is not None:
        slots = sorted(set(body.slots))
        if not slots or len(slots) > 8 or any(not 0 <= h <= 23 for h in slots):
            raise HTTPException(400, "Choose between 1 and 8 slots, each an hour from 0 to 23")
        cfg.slots = slots
    if body.tz is not None:
        try:
            ZoneInfo(body.tz)
        except (ZoneInfoNotFoundError, ValueError):
            raise HTTPException(400, "Unknown time zone")
        cfg.tz = body.tz
    if body.titles is not None:
        cfg.titles = [t.strip()[:80] for t in body.titles if t.strip()]
    if body.skills is not None:
        cfg.skills = [s.strip()[:60] for s in body.skills if s.strip()]
    if body.workStyle is not None:
        if body.workStyle not in WORK_STYLES:
            raise HTTPException(400, "workStyle must be remote, hybrid, onsite or empty")
        cfg.work_style = body.workStyle

    if body.on is True:
        if _cap(user) == 0:
            raise HTTPException(402, "Autopilot is part of Pro. Upgrade to turn it on.")
        missing = [label for ok, label in (
            (_gates(db, user, cfg)["gmailConnected"], "connect Gmail"),
            (_gates(db, user, cfg)["resumeConfirmed"], "confirm your resume"),
            (_gates(db, user, cfg)["phoneVerified"], "verify your phone")) if not ok]
        if missing:
            raise HTTPException(400, "Finish setup first: " + ", ".join(missing))
        cfg.on = True
    elif body.on is False:
        cfg.on = False

    db.commit()
    return _state(db, user)


@router.post("/confirm-resume")
def confirm_resume(user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    if not db.query(Position).filter(Position.user_id == user.id).first():
        raise HTTPException(400, "Add at least one role to your profile before confirming it")
    cfg = _config(db, user)
    cfg.resume_confirmed = True
    db.commit()
    return _state(db, user)


# ── the run ──────────────────────────────────────────────────────────────

def _profile_block(db: Session, user: User) -> tuple[str, list[str]]:
    skills = [s.skill for s in db.query(UserSkill).filter(UserSkill.user_id == user.id)]
    positions = db.query(Position).filter(Position.user_id == user.id).all()
    positions.sort(key=lambda p: p.started_on, reverse=True)
    lines = [f"Name: {user.name or ''}", f"Headline: {user.headline or ''}",
             f"Summary: {(user.summary or '')[:500]}"]
    for p in positions[:3]:
        lines.append(f"- {p.role} at {p.company} ({p.duration_label})")
        lines += [f"    • {b[:180]}" for b in (p.bullets or [])[:4]]
    lines.append("Skills: " + ", ".join(skills[:40]))
    return "\n".join(lines), skills


def _candidates(db: Session, user: User, cfg: AutopilotConfig, skills: list[str]) -> list[tuple[int, Job]]:
    have = {r[0] for r in db.query(Application.fingerprint)
            .filter(Application.user_id == user.id, Application.fingerprint.isnot(None))}
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=FRESH_DAYS)

    q = db.query(Job).filter(Job.active.is_(True), Job.first_seen >= cutoff)
    titles = [t.lower() for t in (cfg.titles or [])]
    if titles:
        q = q.filter(or_(*[Job.title.ilike(f"%{t}%") for t in titles]))
    if cfg.work_style:
        q = q.filter(Job.work_mode == cfg.work_style)
    for auth in (user.work_auth or []):
        col = {"h1b": Job.visa_h1b, "opt": Job.visa_opt, "gc": Job.visa_gc, "usc": Job.visa_usc}.get(auth)
        if col is not None:
            q = q.filter(col != "n")     # 'u' (not stated) stays — most postings say nothing
    rows = q.order_by(Job.first_seen.desc()).limit(300).all()

    want = {s.lower() for s in (cfg.skills or []) or skills}
    scored = []
    for j in rows:
        if j.fingerprint in have:
            continue
        need = {s.lower() for s in (j.required_skills or [])}
        overlap = len(want & need)
        title_hit = sum(1 for t in titles if t in (j.title or "").lower())
        if want and need and overlap == 0 and not title_hit:
            continue
        if not want and not titles:
            continue
        scored.append((title_hit * 3 + overlap, j))
    scored.sort(key=lambda x: (-x[0], x[1].first_seen or dt.datetime.min))
    return scored


def _prepare_one(db: Session, user: User, job: Job, profile: str) -> Application | None:
    key = ai._key("autopilot", user.id, job.fingerprint)
    got = ai._cached(db, key)
    if got is None:
        try:
            got = ai._call(f"""Prepare a job application. Return ONLY minified JSON.

CANDIDATE
{profile}

ROLE: {job.title} at {job.company} ({job.location or 'location not stated'})
JD: {(job.description or '')[:1500]}

SCHEMA {{"subject":"","summary":"","highlights":[""],"cover_letter":""}}

RULES
- Use ONLY facts from the candidate block. NEVER invent metrics, employers, tools or dates.
- subject: "<Job title> — <Candidate name>", under 90 characters.
- summary: 2-3 sentences aimed at this role.
- highlights: 4-6 items, each a reworded bullet from the candidate's own experience that best fits this JD.
- cover_letter: 3 short paragraphs, specific to this role. No "I am writing to express interest".
- If the posting doesn't state pay, don't mention a number.""", 1100, "autopilot", fast=True)
        except HTTPException as e:
            print(f"[autopilot] {user.email} / {job.company}: AI skipped ({e.detail})")
            return None
        if not isinstance(got, dict) or not got.get("cover_letter"):
            return None
        ai._store(db, key, got)

    app = Application(
        user_id=user.id, fingerprint=job.fingerprint, company=job.company, title=job.title,
        location=job.location, status="ready", origin="autopilot",
        tailored_resume={"summary": got.get("summary", ""), "highlights": got.get("highlights", [])},
        cover_letter=got.get("cover_letter", ""),
        form_fields={"subject": got.get("subject") or f"{job.title} — {user.name or 'Application'}"})
    db.add(app); db.commit(); db.refresh(app)
    credits.spend(db, user, 1)
    return app


def prepare_for(db: Session, user: User, cfg: AutopilotConfig) -> AutopilotRun:
    """One slot's worth of work for one user. Never raises for an ordinary
    "nothing to do" — it records why on the run so the user can see it."""
    run = AutopilotRun(user_id=user.id, found=0, prepared=0, skipped=0)
    per_slot = max(1, min(MAX_PER_RUN, _cap(user) // max(1, len(cfg.slots or [1]))))

    def finish(note=None):
        run.note = note
        db.add(run)
        cfg.last_run_at = dt.datetime.now(dt.timezone.utc)
        db.commit(); db.refresh(run)
        return run

    if _cap(user) == 0:
        return finish("Autopilot is part of Pro")
    if len(_queue(db, user)) >= MAX_QUEUE:
        return finish("Your approval queue is full — approve or clear some items")

    profile, skills = _profile_block(db, user)
    if not (cfg.titles or cfg.skills or skills):
        return finish("Add target job titles or skills so Autopilot knows what to look for")

    ranked = _candidates(db, user, cfg, skills)
    run.found = len(ranked)
    if not ranked:
        return finish("No new matching roles this time")

    prepared_today = sum(r.prepared or 0 for r in db.query(AutopilotRun).filter(
        AutopilotRun.user_id == user.id,
        AutopilotRun.ran_at >= dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)))
    room = max(0, _cap(user) - prepared_today)

    for _, job in ranked:
        if run.prepared >= min(per_slot, room):
            break
        if credits.remaining(db, user) < 1:
            return finish("Out of generations this month")
        if _prepare_one(db, user, job, profile):
            run.prepared += 1
        else:
            run.skipped += 1
    run.skipped += max(0, run.found - run.prepared - run.skipped)
    finish(None if run.prepared else "The AI service was unavailable; will retry at your next slot")

    if run.prepared:
        mailer.send(user.email, f"{run.prepared} application{'s' if run.prepared != 1 else ''} ready for your approval",
                    f"Autopilot prepared {run.prepared} application"
                    f"{'s' if run.prepared != 1 else ''} for you.\n\nReview and approve them in one tap:\n"
                    f"{settings.FRONTEND_URL}/#autopilot\n\nNothing is sent until you approve.")
    return run


@router.post("/run")
def run_now(user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    """Run this user's slot immediately — what the toggle does when turned on."""
    cfg = _config(db, user)
    if not cfg.on:
        raise HTTPException(400, "Turn Autopilot on first")
    prepare_for(db, user, cfg)
    return _state(db, user)


# ── the schedule ─────────────────────────────────────────────────────────

def _local_now(cfg: AutopilotConfig, now: dt.datetime) -> dt.datetime:
    try:
        return now.astimezone(ZoneInfo(cfg.tz or "America/Chicago"))
    except ZoneInfoNotFoundError:
        return now.astimezone(ZoneInfo("America/Chicago"))


def is_due(cfg: AutopilotConfig, now: dt.datetime) -> str | None:
    """The slot key ("YYYY-MM-DDTHH", local) if this config should run now and
    hasn't already, else None. Weekdays only — that is what the page promises."""
    local = _local_now(cfg, now)
    if local.weekday() >= 5 or local.hour not in (cfg.slots or []):
        return None
    key = local.strftime("%Y-%m-%dT%H")
    return None if cfg.last_run_key == key else key


def run_due(now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    db = SessionLocal()
    ran = failed = 0
    try:
        try:
            credits.qualify_pending(db)
        except Exception as e:
            print(f"[autopilot] referral sweep failed: {e}")
        cfgs = (db.query(AutopilotConfig).filter(AutopilotConfig.on.is_(True))
                .order_by(AutopilotConfig.last_run_at.asc()).all())
        for cfg in cfgs:
            if ran + failed >= MAX_USERS_PER_TICK:
                break
            key = is_due(cfg, now)
            if not key:
                continue
            user = db.get(User, cfg.user_id)
            if not user:
                continue
            # Claim the slot BEFORE working on it: a crash or a duplicate tick
            # must not turn into a second batch of AI spend for the same hour.
            cfg.last_run_key = key
            db.commit()
            try:
                prepare_for(db, user, cfg)
                ran += 1
            except Exception as e:
                db.rollback()
                failed += 1
                print(f"[autopilot] run failed for {user.email}: {type(e).__name__}: {e}")
        print(f"[autopilot] tick done: {ran} ran, {failed} failed")
        return {"ran": ran, "failed": failed}
    finally:
        db.close()


@router.post("/tick", status_code=202)
def tick(background: BackgroundTasks, wait: bool = False,
         x_cron_secret: str = Header(None)):
    """Called by the scheduler (GitHub Actions) every hour. Closed unless
    CRON_SECRET is set, and compared in constant time."""
    if not settings.CRON_SECRET:
        raise HTTPException(503, "Scheduler is not configured (CRON_SECRET)")
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret.encode(), settings.CRON_SECRET.encode()):
        raise HTTPException(401, "Bad scheduler secret")
    if wait:
        return run_due()
    background.add_task(run_due)
    return {"scheduled": True}


# ── the approval queue ───────────────────────────────────────────────────

def _mine(db: Session, user: User, app_id: str) -> Application:
    a = db.query(Application).filter(Application.id == app_id, Application.user_id == user.id,
                                     Application.origin == "autopilot").first()
    if not a:
        raise HTTPException(404, "Not found")
    return a


@router.get("/queue/{app_id}")
def preview(app_id: str, user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    a = _mine(db, user, app_id)
    job = db.get(Job, a.fingerprint) if a.fingerprint else None
    return {**_item(a, job), "summary": (a.tailored_resume or {}).get("summary", ""),
            "highlights": (a.tailored_resume or {}).get("highlights", []),
            "cover_letter": a.cover_letter}


@router.post("/queue/approve-all")
def approve_all(user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    items = _queue(db, user)
    for a in items:
        a.status, a.note = "opened", "Approved for manual application"
    db.commit()
    return {"approved": len(items), "state": _state(db, user)}


@router.post("/queue/{app_id}/approve")
def approve(app_id: str, user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    a = _mine(db, user, app_id)
    if a.status != "ready":
        raise HTTPException(400, "Already handled")
    a.status, a.note = "opened", "Approved for manual application"
    db.commit()
    job = db.get(Job, a.fingerprint) if a.fingerprint else None
    return {"approved": a.id, "apply_url": job.apply_url if job else None}


@router.delete("/queue/{app_id}")
def skip(app_id: str, user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    a = _mine(db, user, app_id)
    a.status = "skipped"
    db.commit()
    return {"skipped": a.id}
