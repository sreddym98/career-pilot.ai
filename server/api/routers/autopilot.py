# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Autopilot — scheduled job matching with one-tap batch approval.

What runs here is everything up to the send: at each of a user's slots the
server finds fresh roles that clear the user's minimum fit score, tailors a
cover letter and highlights for each, and parks them as `ready` applications.
NOTHING is ever sent unattended and nothing is emailed to an employer (see
decisions: unattended sending from a personal Gmail gets accounts flagged, and
an unchecked AI email is a mistake you can't take back). Approving marks the
application opened and hands back the posting so the user submits it themselves.

It runs on the server, on a schedule, so it works with the tab closed. Free
hosts sleep, so the schedule is driven from outside: a cron (GitHub Actions)
POSTs /api/autopilot/tick with the shared CRON_SECRET, which also wakes the
host. The tick answers immediately and does the work in the background.
"""
import datetime as dt
import hashlib
import hmac
import re
import threading
import time
from collections import Counter
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from api import credits, mailer, matching
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
FRESH_DAYS = 14            # a role must have been first seen this recently ...
MAX_POSTING_AGE_DAYS = 30  # ... and, when the posting states a date, be posted within this
WORK_STYLES = ("", "remote", "hybrid", "onsite")
DEFAULT_MIN_FIT = 60
GRACE_HOURS = 2            # GitHub cron can fire late; a slot is still served up to this many hours after
AI_STRIKES = 2             # consecutive AI outages before a run stops trying (each try can take ~90s)
TICK_AI_DOWN_USERS = 3     # consecutive users whose run hit an AI outage before the whole tick stops
INTERACTIVE_BUDGET_S = 70  # "Run now" is an HTTP request; stay under typical 100s proxy timeouts
STALE_RUN_MIN = 15         # a run still "Running" after this long was cut off (host restart)
RUNNING_NOTE = "Running…"
MAX_PAUSE_DAYS = 90

_active: set[str] = set()          # users with a run in flight in THIS process
_active_lock = threading.Lock()


def _acquire(uid: str) -> bool:
    with _active_lock:
        if uid in _active:
            return False
        _active.add(uid)
        return True


def _release(uid: str):
    with _active_lock:
        _active.discard(uid)


def _aware(d):
    if d is None:
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


# ── config ───────────────────────────────────────────────────────────────

def _config(db: Session, user: User) -> AutopilotConfig:
    cfg = db.get(AutopilotConfig, user.id)
    if not cfg:
        cfg = AutopilotConfig(user_id=user.id, on=False, resume_confirmed=False,
                              slots=[9, 13, 17], titles=[], skills=[], work_style="",
                              min_fit=DEFAULT_MIN_FIT, email_digest=True)
        db.add(cfg); db.commit(); db.refresh(cfg)
    return cfg


def _min_fit(cfg: AutopilotConfig) -> int:
    return DEFAULT_MIN_FIT if cfg.min_fit is None else int(cfg.min_fit)


def phone_required() -> bool:
    """SMS verification only gates Autopilot when Twilio Verify is actually set
    up. Without it the step could never be completed and would lock every user out."""
    return bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN
                and settings.TWILIO_VERIFY_SERVICE_SID)


def email_configured() -> bool:
    return bool(settings.RESEND_API_KEY)


def _gates(db: Session, user: User, cfg: AutopilotConfig) -> dict:
    rows = {r.provider: r for r in db.query(Integration).filter(Integration.user_id == user.id)}
    return {
        "gmailConnected": bool(rows.get("gmail") and rows["gmail"].status == "connected"),
        "phoneVerified": bool(rows.get("phone") and rows["phone"].status == "verified"),
        "resumeConfirmed": bool(cfg.resume_confirmed),
        "phoneRequired": phone_required(),
    }


def _cap(user: User) -> int:
    return DAILY_CAP.get(user.plan, 0)


# ── profile + scoring ────────────────────────────────────────────────────

def _skills_of(db: Session, user: User) -> list[str]:
    return [s.skill for s in db.query(UserSkill).filter(UserSkill.user_id == user.id)]


def _matcher(db: Session, user: User, cfg: AutopilotConfig, skills: list[str] | None = None):
    """The real fit scorer's Profile for this user, or None when there are no
    skills at all (fit can't be computed — callers must say so, not guess)."""
    have = list(skills if skills is not None else _skills_of(db, user))
    seen = {s.lower() for s in have}
    for s in (cfg.skills or []):
        if s and s.lower() not in seen:
            have.append(s); seen.add(s.lower())
    if not have:
        return None
    positions = db.query(Position).filter(Position.user_id == user.id).all()
    return matching.Profile(have, positions, user.headline, list(user.work_auth or []),
                            cfg.work_style or "", list(cfg.titles or []))


def _job_open(job: Job | None) -> bool:
    return bool(job and job.active and job.link_status != "dead")


def _fit_bits(prof, job: Job | None) -> dict:
    if prof is None or job is None:
        return {"fit": None, "matched_skills": [], "missing_skills": [], "work_mode": None, "visa": None}
    s = matching.score_job(prof, job)
    r = s["fit_reasons"] or {}
    return {"fit": s["fit"], "matched_skills": r.get("matched_skills") or [],
            "missing_skills": (r.get("missing_skills") or [])[:8],
            "work_mode": r.get("work_mode"), "visa": r.get("visa")}


def _item(a: Application, job: Job | None, prof=None) -> dict:
    return {"id": a.id, "fingerprint": a.fingerprint, "company": a.company, "title": a.title, "location": a.location,
            "subject": (a.form_fields or {}).get("subject") or f"{a.title} — application",
            "apply_url": job.apply_url if job else None,
            "verified": bool(job and job.link_status == "ok"),
            "matched_at": a.updated_at, **_fit_bits(prof, job)}


def _queue(db: Session, user: User) -> list[Application]:
    return (db.query(Application)
            .filter(Application.user_id == user.id, Application.origin == "autopilot",
                    Application.status == "ready")
            .order_by(Application.updated_at.desc()).all())


def _drop_closed(db: Session, user: User) -> int:
    """Queue items whose posting has since gone inactive (taken down, or its
    link died) can't be applied to — drop them instead of sending the user
    to a dead page."""
    n = 0
    q = _queue(db, user)
    if not q:
        return 0
    jobs = {j.fingerprint: j for j in db.query(Job).filter(
        Job.fingerprint.in_([a.fingerprint for a in q if a.fingerprint]))}
    for a in q:
        if not _job_open(jobs.get(a.fingerprint)):
            a.status, a.note = "skipped", "Posting closed — removed from your Autopilot queue"
            n += 1
    if n:
        db.commit()
    return n


def _settle_runs(db: Session, user: User):
    """A run row still saying "Running…" long after it started was cut off
    (free hosts restart). Say so, rather than leave it spinning forever."""
    if user.id in _active:
        return
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=STALE_RUN_MIN)
    n = 0
    for r in db.query(AutopilotRun).filter(AutopilotRun.user_id == user.id, AutopilotRun.note == RUNNING_NOTE):
        if _aware(r.ran_at) and _aware(r.ran_at) < cutoff:
            r.note = "Interrupted — the server stopped mid-run. Anything prepared before that is in your queue."
            n += 1
    if n:
        db.commit()


def _local_now(cfg: AutopilotConfig, now: dt.datetime) -> dt.datetime:
    try:
        return now.astimezone(ZoneInfo(cfg.tz or "America/Chicago"))
    except ZoneInfoNotFoundError:
        return now.astimezone(ZoneInfo("America/Chicago"))


def next_run_at(cfg: AutopilotConfig, now: dt.datetime | None = None) -> dt.datetime | None:
    """The next weekday slot (UTC), honouring the user's time zone and pause."""
    now = now or dt.datetime.now(dt.timezone.utc)
    local = _local_now(cfg, now)
    tz = local.tzinfo
    for d in range(0, 16):
        day = (local + dt.timedelta(days=d)).date()
        if day.weekday() >= 5 or (cfg.paused_until and day < cfg.paused_until):
            continue
        for h in sorted(cfg.slots or []):
            t = dt.datetime(day.year, day.month, day.day, h, tzinfo=tz)
            if t.astimezone(dt.timezone.utc) > now:
                return t.astimezone(dt.timezone.utc)
    return None


def _state(db: Session, user: User) -> dict:
    cfg = _config(db, user)
    _settle_runs(db, user)
    _drop_closed(db, user)
    q = _queue(db, user)
    jobs = {j.fingerprint: j for j in db.query(Job).filter(
        Job.fingerprint.in_([a.fingerprint for a in q if a.fingerprint]))} if q else {}
    prof = _matcher(db, user, cfg) if q else None
    runs = (db.query(AutopilotRun).filter(AutopilotRun.user_id == user.id)
            .order_by(AutopilotRun.ran_at.desc()).limit(10).all())
    nxt = next_run_at(cfg) if cfg.on else None
    return {
        "on": bool(cfg.on), "slots": sorted(cfg.slots or []), "tz": cfg.tz,
        "titles": cfg.titles or [], "skills": cfg.skills or [],
        "workStyle": cfg.work_style or "", "dailyCap": _cap(user),
        "minFit": _min_fit(cfg),
        "pausedUntil": cfg.paused_until.isoformat() if cfg.paused_until else None,
        "emailDigest": bool(cfg.email_digest), "emailConfigured": email_configured(),
        "needsSkills": not (_skills_of(db, user) or cfg.skills),
        "nextRunAt": nxt.isoformat() if nxt else None,
        "plan": user.plan, **_gates(db, user, cfg),
        "queue": [_item(a, jobs.get(a.fingerprint), prof) for a in q],
        "runs": [{"at": r.ran_at, "found": r.found, "prepared": r.prepared,
                  "skipped": r.skipped, "note": r.note, "details": r.details or {}} for r in runs],
        "credits_remaining": credits.remaining(db, user),
    }


class ConfigIn(BaseModel):
    on: bool | None = None
    slots: list[int] | None = None
    tz: str | None = None
    titles: list[str] | None = Field(default=None, max_length=10)
    skills: list[str] | None = Field(default=None, max_length=30)
    workStyle: str | None = None
    minFit: int | None = None
    pausedUntil: str | None = None        # "YYYY-MM-DD"; "" clears
    emailDigest: bool | None = None


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
    if body.minFit is not None:
        if isinstance(body.minFit, bool) or not 0 <= body.minFit <= 100:
            raise HTTPException(400, "Minimum fit must be a number from 0 to 100")
        cfg.min_fit = int(body.minFit)
    if body.pausedUntil is not None:
        if body.pausedUntil == "":
            cfg.paused_until = None
        else:
            try:
                day = dt.date.fromisoformat(body.pausedUntil)
            except ValueError:
                raise HTTPException(400, "Pause date must look like 2026-10-14")
            today = _local_now(cfg, dt.datetime.now(dt.timezone.utc)).date()
            if day < today:
                raise HTTPException(400, "Pick a pause date that is today or later")
            if day > today + dt.timedelta(days=MAX_PAUSE_DAYS):
                raise HTTPException(400, f"You can pause for at most {MAX_PAUSE_DAYS} days at a time")
            cfg.paused_until = day
    if body.emailDigest is not None:
        cfg.email_digest = bool(body.emailDigest)

    if body.on is True:
        if _cap(user) == 0:
            raise HTTPException(402, "Autopilot is part of Pro. Upgrade to turn it on.")
        missing = [label for ok, label in (
            (_gates(db, user, cfg)["resumeConfirmed"], "confirm your resume"),
            (_gates(db, user, cfg)["phoneVerified"] or not phone_required(), "verify your phone")) if not ok]
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
    skills = _skills_of(db, user)
    positions = db.query(Position).filter(Position.user_id == user.id).all()
    positions.sort(key=lambda p: p.started_on, reverse=True)
    lines = [f"Name: {user.name or ''}", f"Headline: {user.headline or ''}",
             f"Summary: {(user.summary or '')[:500]}"]
    for p in positions[:3]:
        lines.append(f"- {p.role} at {p.company} ({p.duration_label})")
        lines += [f"    • {b[:180]}" for b in (p.bullets or [])[:4]]
    lines.append("Skills: " + ", ".join(skills[:40]))
    return "\n".join(lines), skills


def _candidates(db: Session, user: User, cfg: AutopilotConfig, prof) -> tuple[list[tuple[int, dict, Job]], Counter]:
    """Roles worth preparing, best first, plus a count of what was filtered out
    and why (the run history shows these — no silent drops).

    Uses the same scorer as the job board (matching.score_job): skills, title,
    experience, work mode, and the visa hard-block. A role must clear the
    user's minimum fit; roles the scorer can't score at all are skipped rather
    than queued blind."""
    counts: Counter = Counter()
    if prof is None:
        return [], counts
    now = dt.datetime.now(dt.timezone.utc)
    mine = db.query(Application.fingerprint, Application.company, Application.title).filter(
        Application.user_id == user.id).all()
    have_fp = {r[0] for r in mine if r[0]}
    have_ct = {((r[1] or "").strip().lower(), (r[2] or "").strip().lower()) for r in mine}

    q = db.query(Job).filter(Job.active.is_(True), Job.first_seen >= now - dt.timedelta(days=FRESH_DAYS))
    titles = [t.lower() for t in (cfg.titles or [])]
    if titles:
        q = q.filter(or_(*[Job.title.ilike(f"%{t}%") for t in titles]))
    if cfg.work_style:
        q = q.filter(Job.work_mode == cfg.work_style)
    rows = q.order_by(Job.first_seen.desc()).limit(300).all()

    floor, old = _min_fit(cfg), now - dt.timedelta(days=MAX_POSTING_AGE_DAYS)
    out = []
    for j in rows:
        if j.fingerprint in have_fp or ((j.company or "").strip().lower(), (j.title or "").strip().lower()) in have_ct:
            counts["already_handled"] += 1; continue      # applied, queued, skipped, or a re-listing of one
        if j.link_status == "dead":
            counts["dead_link"] += 1; continue
        if not j.apply_url:
            counts["no_apply_link"] += 1; continue
        if j.posted_at and _aware(j.posted_at) < old:
            counts["stale_posting"] += 1; continue
        s = matching.score_job(prof, j)
        r = s["fit_reasons"] or {}
        if r.get("blocked"):
            counts["visa_blocked"] += 1; continue
        if s["fit"] is None:
            counts["not_scorable"] += 1; continue
        if s["fit"] < floor:
            counts["below_min_fit"] += 1; continue
        out.append((s["fit"], r, j))
    out.sort(key=lambda x: (-x[0], x[2].link_status != "ok",
                            -(_aware(x[2].first_seen) or now).timestamp()))
    return out, counts


_PLACEHOLDER = re.compile(r"\[[^\]\n]{2,40}\]|\{\{|\}\}|lorem ipsum|\bTBD\b|<[A-Za-z ]{3,30}>", re.I)
_FIGURE = re.compile(r"\$\s?\d[\d,.]*\s?[kKmMbB]?\b|\d[\d,.]*\s?%")


def _norm(s: str) -> str:
    return re.sub(r"[\s,]", "", (s or "").lower())


def _clean_ai(got, source_text: str, job: Job, user: User) -> dict | None:
    """The model's output is untrusted. Accept only well-formed drafts with no
    leftover template placeholders and no dollar or percentage figures that the
    candidate's own profile (or the posting) doesn't contain — the prompt says
    never to invent metrics, this enforces it. None = reject."""
    if not isinstance(got, dict):
        return None
    letter = got.get("cover_letter")
    if not isinstance(letter, str) or len(letter.strip()) < 80:
        return None
    hl = got.get("highlights")
    if not isinstance(hl, list):
        return None
    highlights = [h.strip()[:300] for h in hl if isinstance(h, str) and h.strip()][:6]
    if not highlights:
        return None
    summary = got.get("summary") if isinstance(got.get("summary"), str) else ""
    subject = got.get("subject") if isinstance(got.get("subject"), str) else ""
    subject = subject.strip()[:120] or f"{job.title} — {user.name or 'Application'}"
    blob = " ".join([letter, summary, subject, *highlights])
    if _PLACEHOLDER.search(blob):
        return None
    src = _norm(source_text)
    if any(_norm(m) not in src for m in _FIGURE.findall(blob)):
        return None
    return {"subject": subject, "summary": summary.strip()[:800], "highlights": highlights,
            "cover_letter": letter.strip()[:4000]}


def _prepare_one(db: Session, user: User, job: Job, profile: str) -> tuple[Application | None, str | None]:
    """(application, None) or (None, reason) with reason in duplicate |
    ai_unavailable | ai_invalid. A failed attempt costs the user nothing."""
    source = profile + "\n" + (job.description or "") + "\n" + (job.title or "")
    key = ai._key("autopilot", user.id, job.fingerprint, hashlib.sha256(profile.encode()).hexdigest()[:12])
    clean = None
    cached = ai._cached(db, key)
    if cached is not None:
        clean = _clean_ai(cached, source, job, user)
    if clean is None:
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
            return None, "ai_unavailable"
        except Exception as e:                       # one bad call must not end the run
            print(f"[autopilot] {user.email} / {job.company}: AI error {type(e).__name__}: {e}")
            return None, "ai_unavailable"
        clean = _clean_ai(got, source, job, user)
        if clean is None:
            print(f"[autopilot] {user.email} / {job.company}: draft rejected by validation")
            return None, "ai_invalid"
        ai._store(db, key, clean)

    # Re-check right before writing: two overlapping runs must not double-queue.
    if db.query(Application.id).filter(Application.user_id == user.id,
                                       Application.fingerprint == job.fingerprint).first():
        return None, "duplicate"
    app = Application(
        user_id=user.id, fingerprint=job.fingerprint, company=job.company, title=job.title,
        location=job.location, status="ready", origin="autopilot",
        tailored_resume={"summary": clean["summary"], "highlights": clean["highlights"]},
        cover_letter=clean["cover_letter"], form_fields={"subject": clean["subject"]})
    db.add(app)
    credits.spend(db, user, 1)          # one commit: the queued item and its generation
    db.refresh(app)
    return app, None


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _send_digest(db: Session, user: User, cfg: AutopilotConfig, slot_key: str) -> str | None:
    """One email a day, after the user's LAST slot, only if something was
    prepared in the last 24h and is still waiting. Only reported as sent when
    the mail provider actually accepted it."""
    if not (cfg.email_digest and email_configured() and slot_key):
        return None
    if int(slot_key[-2:]) != max(cfg.slots or [0]) or cfg.last_digest_on == slot_key[:10]:
        return None
    q = _queue(db, user)
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
    if not q or not any(_aware(a.updated_at) and _aware(a.updated_at) >= since for a in q):
        return None
    jobs = {j.fingerprint: j for j in db.query(Job).filter(Job.fingerprint.in_([a.fingerprint for a in q if a.fingerprint]))}
    prof = _matcher(db, user, cfg)
    lines = []
    for a in q[:10]:
        fit = _fit_bits(prof, jobs.get(a.fingerprint))["fit"]
        lines.append(f"  - {a.title} at {a.company}" + (f" ({fit}% fit)" if fit is not None else ""))
    more = f"\n  ...and {len(q) - 10} more" if len(q) > 10 else ""
    body = (f"{_plural(len(q), 'application')} prepared by Autopilot {'is' if len(q) == 1 else 'are'} waiting for your review:\n\n"
            + "\n".join(lines) + more
            + f"\n\nReview them here: {settings.FRONTEND_URL}/#autopilot\n\n"
              "Nothing has been sent to any employer. Approving an application opens the posting so you can submit it yourself.")
    if mailer.send(user.email, f"Autopilot: {_plural(len(q), 'application')} waiting for your review", body):
        cfg.last_digest_on = slot_key[:10]
        db.commit()
        return "sent"
    return "failed"


def prepare_for(db: Session, user: User, cfg: AutopilotConfig, budget_s: float | None = None,
                slot_key: str | None = None) -> AutopilotRun:
    """One slot's worth of work for one user. Never raises for an ordinary
    "nothing to do" — it records why on the run so the user can see it. The run
    row exists from the start (so a cut-off run is visible) and its counts are
    updated as each item lands."""
    t0 = time.monotonic()
    _settle_runs(db, user)
    run = AutopilotRun(user_id=user.id, found=0, prepared=0, skipped=0, note=RUNNING_NOTE, details={},
                       ran_at=dt.datetime.now(dt.timezone.utc))
    db.add(run); db.commit(); db.refresh(run)
    details: dict = {}

    def finish(note=None):
        run.note = note
        run.details = dict(details)      # reassign: in-place JSON edits aren't tracked
        cfg.last_run_at = dt.datetime.now(dt.timezone.utc)
        db.commit(); db.refresh(run)
        return run

    try:
        dropped = _drop_closed(db, user)
        if dropped:
            details["dropped_closed"] = dropped
        if _cap(user) == 0:
            return finish("Autopilot is part of Pro")
        queue_len = len(_queue(db, user))
        if queue_len >= MAX_QUEUE:
            return finish("Your approval queue is full — approve or clear some items")

        profile, skills = _profile_block(db, user)
        prof = _matcher(db, user, cfg, skills)
        if prof is None:
            details["needs_skills"] = True
            return finish("Add skills to your profile — Autopilot needs them to score how well each role fits you")

        eligible, counts = _candidates(db, user, cfg, prof)
        run.found = len(eligible)
        details["filtered"] = dict(counts)
        details["min_fit"] = _min_fit(cfg)
        if not eligible:
            return finish(f"Nothing new at or above your {_min_fit(cfg)}% minimum fit" if counts.get("below_min_fit")
                          else "No new matching roles this time")

        per_slot = max(1, min(MAX_PER_RUN, _cap(user) // max(1, len(cfg.slots or [1]))))
        prepared_today = sum(r.prepared or 0 for r in db.query(AutopilotRun).filter(
            AutopilotRun.user_id == user.id, AutopilotRun.id != run.id,
            AutopilotRun.ran_at >= dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)))
        room = max(0, _cap(user) - prepared_today)
        if room == 0:
            return finish(f"Daily limit reached ({_cap(user)}/day) — more will be prepared tomorrow")
        limit = min(per_slot, room, MAX_QUEUE - queue_len)

        why: Counter = Counter()
        strikes, out_of_credits, out_of_time = 0, False, False
        for _fit, _reasons, job in eligible:
            if run.prepared >= limit:
                break
            if budget_s and time.monotonic() - t0 > budget_s:
                out_of_time = True; break
            if credits.remaining(db, user) < 1:
                out_of_credits = True; break
            app, reason = _prepare_one(db, user, job, profile)
            if app:
                run.prepared += 1; strikes = 0
            else:
                run.skipped += 1; why[reason] += 1
                strikes = strikes + 1 if reason == "ai_unavailable" else 0
            db.commit()                                   # progress survives a cut-off
            if strikes >= AI_STRIKES:
                break
        details.update({k: v for k, v in why.items()})
        details["not_attempted"] = max(0, run.found - run.prepared - run.skipped)

        note = None
        if out_of_credits:
            note = "Out of generations this month"
        elif out_of_time:
            note = "Stopped early to stay within the time limit — the rest will be prepared next run"
        elif not run.prepared:
            if why["ai_unavailable"]:
                note = "The AI service was busy or unavailable; will retry at your next slot"
            elif why["ai_invalid"]:
                note = "The AI's drafts failed our checks (invented figures or leftover placeholders), so nothing was queued"
        if slot_key:
            d = _send_digest(db, user, cfg, slot_key)
            if d:
                details["digest"] = d
        return finish(note)
    except Exception as e:
        db.rollback()
        print(f"[autopilot] run error for {user.email}: {type(e).__name__}: {e}")
        details["error"] = True
        try:
            run = db.get(AutopilotRun, run.id) or run
            return finish("Stopped by an unexpected error — nothing was sent. Anything prepared before that is in your queue.")
        except Exception:
            db.rollback()
            return run


@router.post("/run")
def run_now(user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    """Run this user's slot immediately — what the toggle does when turned on."""
    cfg = _config(db, user)
    if not cfg.on:
        raise HTTPException(400, "Turn Autopilot on first")
    if not _acquire(user.id):
        raise HTTPException(409, "A run is already in progress")
    try:
        # A run just happened: don't let the scheduler serve this hour's slot again.
        here = _local_now(cfg, dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%dT%H")
        cfg.last_run_key = max(cfg.last_run_key or "", here)
        db.commit()
        prepare_for(db, user, cfg, budget_s=INTERACTIVE_BUDGET_S)
    finally:
        _release(user.id)
    return _state(db, user)


@router.get("/preview")
def preview_next(user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    """What the next run would prepare, using the real matcher. No AI call, no
    credits spent, nothing written."""
    cfg = _config(db, user)
    prof = _matcher(db, user, cfg)
    eligible, counts = _candidates(db, user, cfg, prof)
    per_slot = max(1, min(MAX_PER_RUN, _cap(user) // max(1, len(cfg.slots or [1])))) if _cap(user) else 0
    nxt = next_run_at(cfg)
    return {
        "minFit": _min_fit(cfg), "needsSkills": prof is None,
        "eligible": len(eligible), "filtered": dict(counts),
        "perRun": per_slot, "queueFull": len(_queue(db, user)) >= MAX_QUEUE,
        "nextRunAt": nxt.isoformat() if (nxt and cfg.on) else None,
        "pausedUntil": cfg.paused_until.isoformat() if cfg.paused_until else None,
        "roles": [{"fingerprint": j.fingerprint, "company": j.company, "title": j.title,
                   "location": j.location, "fit": fit, "verified": j.link_status == "ok",
                   "matched_skills": r.get("matched_skills") or [],
                   "missing_skills": (r.get("missing_skills") or [])[:8],
                   "thisRun": i < per_slot}
                  for i, (fit, r, j) in enumerate(eligible[:10])],
    }


# ── the schedule ─────────────────────────────────────────────────────────

def is_due(cfg: AutopilotConfig, now: dt.datetime) -> str | None:
    """The slot key ("YYYY-MM-DDTHH", local) if this config should run now and
    hasn't already, else None. Weekdays only, and not while paused.

    The hourly cron is best-effort (GitHub delays scheduled runs, and a slot
    inside a spring-forward gap never occurs on the clock), so a slot is still
    served for GRACE_HOURS after its hour. Keys sort chronologically, so "served"
    is just "last_run_key >= this slot"."""
    local = _local_now(cfg, now)
    if local.weekday() >= 5:
        return None
    if cfg.paused_until and local.date() < cfg.paused_until:
        return None
    hours = [h for h in (cfg.slots or []) if 0 <= local.hour - h <= GRACE_HOURS]
    if not hours:
        return None
    key = f"{local.strftime('%Y-%m-%d')}T{max(hours):02d}"
    return None if (cfg.last_run_key or "") >= key else key


def run_due(now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    db = SessionLocal()
    ran = failed = ai_down_streak = 0
    try:
        try:
            credits.qualify_pending(db)
        except Exception as e:
            print(f"[autopilot] referral sweep failed: {e}")
        # Never-run users first (NULL sorts last on Postgres unless told otherwise).
        cfgs = (db.query(AutopilotConfig).filter(AutopilotConfig.on.is_(True))
                .order_by(AutopilotConfig.last_run_at.asc().nullsfirst()).all())
        for cfg in cfgs:
            if ran + failed >= MAX_USERS_PER_TICK:
                break
            if ai_down_streak >= TICK_AI_DOWN_USERS:
                print("[autopilot] AI looks down; stopping this tick — unserved slots retry next hour")
                break
            key = is_due(cfg, now)
            if not key:
                continue
            uid = cfg.user_id
            user = db.get(User, uid)
            if not user or not _acquire(uid):
                continue
            try:
                # Claim the slot BEFORE working on it: a crash or a duplicate tick
                # must not turn into a second batch of AI spend for the same hour.
                cfg.last_run_key = key
                db.commit()
                run = prepare_for(db, user, cfg, slot_key=key)
                if (run.details or {}).get("error"):
                    failed += 1
                else:
                    ran += 1
                d = run.details or {}
                ai_down_streak = ai_down_streak + 1 if (d.get("ai_unavailable") and not run.prepared) else 0
            except Exception as e:
                db.rollback()
                failed += 1
                print(f"[autopilot] run failed for user {uid}: {type(e).__name__}: {e}")
            finally:
                _release(uid)
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


@router.post("/ingest", status_code=202)
def ingest_now(mode: str = "full", x_cron_secret: str = Header(None)):
    """Kick off a job import inside the API (same code the GitHub job runs)."""
    if not settings.CRON_SECRET:
        raise HTTPException(503, "Scheduler is not configured (CRON_SECRET)")
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret.encode(), settings.CRON_SECRET.encode()):
        raise HTTPException(401, "Bad scheduler secret")
    if mode not in ("full", "fast"):
        raise HTTPException(400, "mode must be full or fast")
    from api import ingest_job
    return {"started": ingest_job.start(mode), "running": ingest_job.running()}


@router.post("/diag")
def diag(x_cron_secret: str = Header(None)):
    """Deployment self-check for the operator (run from GitHub Actions). Says
    which integrations are configured and makes one tiny live AI call. Never
    returns a secret value."""
    if not settings.CRON_SECRET:
        raise HTTPException(503, "Scheduler is not configured (CRON_SECRET)")
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret.encode(), settings.CRON_SECRET.encode()):
        raise HTTPException(401, "Bad scheduler secret")
    from sqlalchemy import text as _t
    from api.db import engine
    out = {"env": settings.ENV, "frontend_url": settings.FRONTEND_URL}
    try:
        with engine.connect() as c: c.execute(_t("SELECT 1"))
        out["database"] = "ok"
    except Exception as e:
        out["database"] = f"FAILED: {type(e).__name__}"
    out["ai_provider"] = ai.provider()
    try:
        r = ai._call('Reply with the JSON {"ok": true}', 40, "diag", fast=True)
        out["ai_live_call"] = "ok" if r else "empty reply"
    except HTTPException as e:
        out["ai_live_call"] = f"FAILED: {e.detail}"
    except Exception as e:
        out["ai_live_call"] = f"FAILED: {type(e).__name__}"
    from api.models import Job
    from api import ingest_job
    dbs = SessionLocal()
    try:
        out["jobs_live"] = dbs.query(Job).filter(Job.active.is_(True)).count()
    finally:
        dbs.close()
    out["ingest_running"] = ingest_job.running()
    out["configured"] = {
        "stripe_secret": bool(settings.STRIPE_SECRET_KEY),
        "stripe_webhook": bool(settings.STRIPE_WEBHOOK_SECRET),
        "stripe_prices": all([settings.STRIPE_PRICE_PRO_MONTHLY, settings.STRIPE_PRICE_PRO_3MO,
                              settings.STRIPE_PRICE_PRO_6MO, settings.STRIPE_PRICE_RECRUITER,
                              settings.STRIPE_PRICE_EVAL]),
        "resend_email": bool(settings.RESEND_API_KEY),
        "twilio_verify": phone_required(),
        "gmail_oauth": bool(settings.GMAIL_CLIENT_ID and settings.GMAIL_CLIENT_SECRET),
        "admin_emails": bool(settings.ADMIN_EMAILS),
    }
    return out


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
    prof = _matcher(db, user, _config(db, user))
    return {**_item(a, job, prof), "summary": (a.tailored_resume or {}).get("summary", ""),
            "highlights": (a.tailored_resume or {}).get("highlights", []),
            "cover_letter": a.cover_letter}


@router.post("/queue/approve-all")
def approve_all(user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    dropped = _drop_closed(db, user)          # never approve a posting that has closed
    items = _queue(db, user)
    for a in items:
        a.status, a.note = "opened", "Approved for manual application"
    db.commit()
    return {"approved": len(items), "dropped": dropped, "state": _state(db, user)}


@router.post("/queue/{app_id}/approve")
def approve(app_id: str, user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    a = _mine(db, user, app_id)
    if a.status != "ready":
        raise HTTPException(400, "Already handled")
    job = db.get(Job, a.fingerprint) if a.fingerprint else None
    if not _job_open(job):
        a.status, a.note = "skipped", "Posting closed — removed from your Autopilot queue"
        db.commit()
        raise HTTPException(409, "This posting has closed, so it was removed from your queue")
    a.status, a.note = "opened", "Approved for manual application"
    db.commit()
    return {"approved": a.id, "apply_url": job.apply_url}


@router.delete("/queue/{app_id}")
def skip(app_id: str, user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    a = _mine(db, user, app_id)
    a.status = "skipped"
    db.commit()
    return {"skipped": a.id}
