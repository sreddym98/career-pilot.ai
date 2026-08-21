# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""People I Know.

A referral is the single highest-yield move in a job search, and the thing
that stops people making one is not knowing who they already know at the
company. This is that list, kept by hand, grouped by employer.

Deliberately not scraped from anywhere. These are real people's names and
jobs, entered by the one person entitled to write them down.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session
from api.db import get_db
from api.access import require_seeker
from api.models import User, Connection, Job

router = APIRouter(prefix="/api/connections", tags=["connections"],
                   dependencies=[Depends(require_seeker)])

MAX_CONNECTIONS = 500


class ConnectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    company: str = Field(min_length=1, max_length=120)
    role: str | None = Field(default=None, max_length=120)
    degree: int = Field(default=1, ge=1, le=3)
    how_known: str | None = Field(default=None, max_length=300)


def _out(c: Connection) -> dict:
    return {"id": c.id, "name": c.name, "role": c.role, "company": c.company,
            "degree": c.degree, "how_known": c.how_known}


@router.get("")
def list_connections(user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    """Grouped by company, with a live count of what each one is currently
    hiring for — that pairing is the whole point of the page."""
    rows = db.query(Connection).filter(Connection.user_id == user.id)\
             .order_by(Connection.company, Connection.degree).all()

    by_company: dict[str, list] = {}
    for c in rows:
        by_company.setdefault(c.company, []).append(_out(c))

    openings = {}
    if by_company:
        counts = db.query(Job.company, func.count(Job.fingerprint))\
                   .filter(Job.active == True,
                           func.lower(Job.company).in_([c.lower() for c in by_company]))\
                   .group_by(Job.company).all()
        for company, n in counts:
            # SQL groups by the raw column, so "Cognizant" and "cognizant"
            # arrive as separate rows. Add them up rather than letting the
            # second one overwrite the first.
            openings[company.lower()] = openings.get(company.lower(), 0) + n

    return {"total": len(rows),
            "companies": [{"company": company,
                           "open_roles": openings.get(company.lower(), 0),
                           "people": people}
                          for company, people in sorted(by_company.items())]}


@router.post("")
def add_connection(body: ConnectionIn, user: User = Depends(require_seeker),
                   db: Session = Depends(get_db)):
    name, company = body.name.strip(), body.company.strip()
    existing = db.query(Connection).filter(
        Connection.user_id == user.id,
        func.lower(Connection.name) == name.lower(),
        func.lower(Connection.company) == company.lower()).first()
    if existing:
        raise HTTPException(409, f"{name} is already on your list for {company}")

    if db.query(Connection).filter(Connection.user_id == user.id).count() >= MAX_CONNECTIONS:
        raise HTTPException(400, f"That's {MAX_CONNECTIONS} people — more than a referral list can usefully hold")

    row = Connection(user_id=user.id, name=name, company=company,
                     role=(body.role or "").strip() or None,
                     degree=body.degree,
                     how_known=(body.how_known or "").strip() or None)
    db.add(row); db.commit(); db.refresh(row)
    return _out(row)


@router.put("/{cid}")
def edit_connection(cid: str, body: ConnectionIn, user: User = Depends(require_seeker),
                    db: Session = Depends(get_db)):
    row = db.query(Connection).filter(Connection.id == cid,
                                      Connection.user_id == user.id).first()
    if not row: raise HTTPException(404, "That person isn't on your list")
    row.name = body.name.strip()
    row.company = body.company.strip()
    row.role = (body.role or "").strip() or None
    row.degree = body.degree
    row.how_known = (body.how_known or "").strip() or None
    db.commit(); db.refresh(row)
    return _out(row)


@router.delete("/{cid}")
def remove_connection(cid: str, user: User = Depends(require_seeker),
                      db: Session = Depends(get_db)):
    row = db.query(Connection).filter(Connection.id == cid,
                                      Connection.user_id == user.id).first()
    if not row: raise HTTPException(404, "That person isn't on your list")
    db.delete(row); db.commit()
    return {"deleted": True}
