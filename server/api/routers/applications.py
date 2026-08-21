# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""The application tracker.

Two different vocabularies meet here and it's worth being explicit about it.
The database speaks the pipeline: what *we* have done with an application
(queued → preparing → ready → submitted). The tracker UI speaks the outcome:
what the *employer* did (sent → reply → interview → offer/closed).

They aren't the same axis, but users only ever think in the second one, so the
short codes are accepted on the way in and echoed back alongside the canonical
status. The client never has to know the mapping exists.
"""
import datetime as dt
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from api.db import get_db
from api.access import require_seeker
from api.models import User, Application, Job

router = APIRouter(prefix="/api/applications", tags=["applications"],
                   dependencies=[Depends(require_seeker)])

STATUSES = ["queued", "preparing", "needs_input", "ready",
            "submitted", "responded", "interview", "selected", "rejected"]

# What the tracker calls each stage ⇄ what the pipeline calls it.
SHORT = {"submitted": "sent", "responded": "reply", "interview": "intv",
         "selected": "offer", "rejected": "closed"}
LONG = {v: k for k, v in SHORT.items()}

MAX_TRACKED = 2000      # a tracker, not a scraper's dumping ground


class ApplicationIn(BaseModel):
    company: str
    title: str
    location: str | None = None
    status: str = "submitted"
    note: str | None = None
    fingerprint: str | None = None
    blocker: str | None = None


class StatusIn(BaseModel):
    status: str
    note: str | None = None
    blocker: str | None = None


def _canonical(status: str) -> str:
    s = (status or "").strip().lower()
    s = LONG.get(s, s)
    if s not in STATUSES:
        raise HTTPException(400, f"Unknown status '{status}'. "
                                 f"Use one of: {', '.join(STATUSES)}")
    return s


def _out(a: Application) -> dict:
    return {"id": a.id, "company": a.company, "title": a.title,
            "location": a.location, "status": a.status,
            "short": SHORT.get(a.status, a.status), "note": a.note,
            "blocker": a.blocker, "fingerprint": a.fingerprint,
            "applied_at": a.applied_at, "updated_at": a.updated_at}


@router.get("")
def list_applications(status: str | None = Query(None),
                      user: User = Depends(require_seeker),
                      db: Session = Depends(get_db)):
    q = db.query(Application).filter(Application.user_id == user.id)
    if status:
        q = q.filter(Application.status == _canonical(status))
    rows = q.order_by(Application.updated_at.desc()).all()
    counts = {}
    for a in rows:
        counts[SHORT.get(a.status, a.status)] = counts.get(SHORT.get(a.status, a.status), 0) + 1
    return {"total": len(rows), "counts": counts,
            "applications": [_out(a) for a in rows]}


@router.post("")
def track(body: ApplicationIn, user: User = Depends(require_seeker),
          db: Session = Depends(get_db)):
    """Upsert. Marking the same posting twice is a correction, not a duplicate
    row — the tracker is a picture of where things stand, not an event log."""
    company = body.company.strip()
    title = body.title.strip()
    if not company or not title:
        raise HTTPException(400, "An application needs a company and a job title")

    status = _canonical(body.status)
    row = _find(db, user.id, company, title, body.fingerprint)

    if not row:
        n = db.query(Application).filter(Application.user_id == user.id).count()
        if n >= MAX_TRACKED:
            raise HTTPException(400, f"You're tracking {MAX_TRACKED} applications. Clear some out first.")
        row = Application(user_id=user.id, company=company, title=title)
        db.add(row)

    row.location = body.location
    row.note = body.note
    row.blocker = body.blocker
    row.status = status
    # Only link a fingerprint we actually ingested — the column is a real
    # foreign key, and a posting found elsewhere has no row to point at.
    if body.fingerprint and db.query(Job).filter(Job.fingerprint == body.fingerprint).first():
        row.fingerprint = body.fingerprint
    if status not in ("queued", "preparing", "needs_input", "ready") and not row.applied_at:
        row.applied_at = dt.datetime.now(dt.timezone.utc)

    db.commit(); db.refresh(row)
    return _out(row)


@router.patch("/{app_id}")
def set_status(app_id: str, body: StatusIn, user: User = Depends(require_seeker),
               db: Session = Depends(get_db)):
    row = db.query(Application).filter(Application.id == app_id,
                                       Application.user_id == user.id).first()
    if not row: raise HTTPException(404, "Application not found")
    row.status = _canonical(body.status)
    if body.note is not None: row.note = body.note
    if body.blocker is not None: row.blocker = body.blocker
    if row.status not in ("queued", "preparing", "needs_input", "ready") and not row.applied_at:
        row.applied_at = dt.datetime.now(dt.timezone.utc)
    db.commit(); db.refresh(row)
    return _out(row)


@router.delete("/{app_id}")
def untrack(app_id: str, user: User = Depends(require_seeker),
            db: Session = Depends(get_db)):
    row = db.query(Application).filter(Application.id == app_id,
                                       Application.user_id == user.id).first()
    if not row: raise HTTPException(404, "Application not found")
    db.delete(row); db.commit()
    return {"deleted": True}


def _find(db: Session, user_id: str, company: str, title: str, fingerprint: str | None):
    """Same posting, however it was reached. The fingerprint is authoritative
    when we have one; otherwise company + title is what the user typed and
    what they'd recognise as the same thing."""
    if fingerprint:
        hit = db.query(Application).filter(Application.user_id == user_id,
                                           Application.fingerprint == fingerprint).first()
        if hit: return hit
    return db.query(Application).filter(
        Application.user_id == user_id,
        func.lower(Application.company) == company.lower(),
        func.lower(Application.title) == title.lower()).first()
