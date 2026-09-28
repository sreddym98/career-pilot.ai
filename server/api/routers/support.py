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
import threading
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from api.db import get_db
from api.auth import current_user
from api.access import require_admin
from api.models import User, SupportTicket
from api.ratelimit import per_user
from api.settings import settings
from api import mailer

router = APIRouter(prefix="/api/support", tags=["support"])

# Committed response times. If you can't actually hit these, don't put
# them in the UI — an unmet SLA is worse than none.
SLA_HOURS = {"priority": 4, "standard": 48}


class TicketIn(BaseModel):
    subject: str = Field(min_length=3, max_length=200)
    message: str = Field(min_length=10, max_length=5000)


def _notify_support(ticket_id: str, priority: str, plan: str, email: str,
                    subject: str, message: str) -> None:
    """Best-effort email to the team. Never raises."""
    try:
        if not settings.SUPPORT_EMAIL:
            return
        tag = "[PRIORITY] " if priority == "priority" else ""
        clean = " ".join(subject.split())[:150]       # no header-injecting newlines
        mailer.send(settings.SUPPORT_EMAIL, f"{tag}Support: {clean}",
                    f"Ticket {ticket_id}\nFrom: {email} (plan: {plan}, {priority}, "
                    f"SLA {SLA_HOURS[priority]}h)\n\n{message}")
    except Exception as e:
        print(f"[support] notification failed: {e}")


@router.post("", dependencies=[Depends(per_user("support", "RATE_SUPPORT", "RATE_SUPPORT_WINDOW_S"))])
def submit_ticket(body: TicketIn, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    priority = "priority" if user.plan in ("pro", "recruiter") else "standard"
    t = SupportTicket(user_id=user.id, plan_at_submission=user.plan,
                      priority=priority, subject=body.subject.strip(),
                      message=body.message.strip())
    db.add(t); db.commit(); db.refresh(t)
    if settings.SUPPORT_EMAIL:
        # Off the request path: Resend can take seconds and mail must not slow
        # or fail the ticket.
        threading.Thread(target=_notify_support, daemon=True,
                         args=(t.id, priority, user.plan, user.email,
                               t.subject, t.message)).start()
    return {"id": t.id, "priority": priority,
            "sla_hours": SLA_HOURS[priority],
            "created_at": t.created_at}


@router.get("/mine")
def my_tickets(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(SupportTicket).filter(SupportTicket.user_id == user.id)\
             .order_by(SupportTicket.created_at.desc()).all()
    return [{"id": t.id, "subject": t.subject, "status": t.status,
            "priority": t.priority, "created_at": t.created_at} for t in rows]


@router.get("/queue", dependencies=[Depends(require_admin)])
def support_queue(priority: str = None, db: Session = Depends(get_db)):
    """For whoever is answering tickets. Staff only: every user's messages are
    in here, so it sits behind ADMIN_EMAILS."""
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


@router.post("/{ticket_id}/resolve", dependencies=[Depends(require_admin)])
def resolve_ticket(ticket_id: str, db: Session = Depends(get_db)):
    t = db.query(SupportTicket).get(ticket_id)
    if not t:
        raise HTTPException(404, "Ticket not found")
    t.status = "closed"
    t.resolved_at = dt.datetime.now(dt.timezone.utc)
    db.commit()
    return {"resolved": True}
