# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Support requests.

This is the actual mechanism behind "Priority support" on the pricing
page. Without it, that line is a promise with nothing behind it — the
same class of problem as the recruiter-email flow claiming "resume
attached" when nothing was. `priority` is read from the user's plan at
the moment they submit, not something they can set themselves.
"""
import datetime as dt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from api.db import get_db
from api.auth import current_user
from api.models import User, SupportTicket

router = APIRouter(prefix="/api/support", tags=["support"])

# Committed response times. If you can't actually hit these, don't put
# them in the UI — an unmet SLA is worse than none.
SLA_HOURS = {"priority": 4, "standard": 48}


class TicketIn(BaseModel):
    subject: str = Field(min_length=3, max_length=200)
    message: str = Field(min_length=10, max_length=5000)


@router.post("")
def submit_ticket(body: TicketIn, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    priority = "priority" if user.plan in ("pro", "recruiter") else "standard"
    t = SupportTicket(user_id=user.id, plan_at_submission=user.plan,
                      priority=priority, subject=body.subject.strip(),
                      message=body.message.strip())
    db.add(t); db.commit(); db.refresh(t)
    return {"id": t.id, "priority": priority,
            "sla_hours": SLA_HOURS[priority],
            "created_at": t.created_at}


@router.get("/mine")
def my_tickets(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(SupportTicket).filter(SupportTicket.user_id == user.id)\
             .order_by(SupportTicket.created_at.desc()).all()
    return [{"id": t.id, "subject": t.subject, "status": t.status,
            "priority": t.priority, "created_at": t.created_at} for t in rows]


@router.get("/queue")
def support_queue(priority: str = None, db: Session = Depends(get_db)):
    """For whoever is answering tickets. No auth gate here on purpose is
    wrong for production — wire this behind an admin check before you
    deploy; it's unguarded now only so you can see it work locally."""
    q = db.query(SupportTicket).filter(SupportTicket.status == "open")
    if priority:
        q = q.filter(SupportTicket.priority == priority)
    # Priority tickets first, oldest first within each tier — that's what
    # "priority" has to mean in the queue, not just in the marketing copy.
    rows = q.order_by(SupportTicket.priority.asc(), SupportTicket.created_at.asc()).all()
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for t in rows:
        created = t.created_at if t.created_at.tzinfo else t.created_at.replace(tzinfo=dt.timezone.utc)
        age_hours = (now - created).total_seconds() / 3600
        sla = SLA_HOURS[t.priority]
        out.append({"id": t.id, "subject": t.subject, "message": t.message,
                    "priority": t.priority, "plan": t.plan_at_submission,
                    "age_hours": round(age_hours, 1), "sla_hours": sla,
                    "overdue": age_hours > sla})
    return out


@router.post("/{ticket_id}/resolve")
def resolve_ticket(ticket_id: str, db: Session = Depends(get_db)):
    t = db.query(SupportTicket).get(ticket_id)
    if not t:
        raise HTTPException(404, "Ticket not found")
    t.status = "closed"
    t.resolved_at = dt.datetime.now(dt.timezone.utc)
    db.commit()
    return {"resolved": True}
