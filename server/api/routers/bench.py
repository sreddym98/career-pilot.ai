# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""The recruiter's bench.

Stored as one document per account (see models.BenchDoc). The plan's cap is
enforced here, not just in the UI: a cap the client alone checks is a
suggestion.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from api.db import get_db
from api.access import require_recruiter, assert_bench_room
from api.models import User, BenchDoc

router = APIRouter(prefix="/api/bench", tags=["bench"],
                   dependencies=[Depends(require_recruiter)])

MAX_CANDIDATES = 500      # absolute ceiling, even on an uncapped plan
MAX_SUBMISSIONS = 5000


class BenchIn(BaseModel):
    candidates: list[dict]
    submissions: list[dict] = []


def _out(d: BenchDoc | None) -> dict:
    return {"exists": d is not None,
            "candidates": (d.candidates if d else None) or [],
            "submissions": (d.submissions if d else None) or []}


@router.get("")
def get_bench(user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    return _out(db.get(BenchDoc, user.id))


@router.put("")
def save_bench(body: BenchIn, user: User = Depends(require_recruiter),
               db: Session = Depends(get_db)):
    """Replace the whole bench. Growing past the plan's cap is a 402; shrinking
    or editing an over-cap bench (a plan that was downgraded) is always allowed."""
    doc = db.get(BenchDoc, user.id)
    had = len((doc.candidates if doc else None) or [])
    n = len(body.candidates)
    if n > MAX_CANDIDATES or len(body.submissions) > MAX_SUBMISSIONS:
        raise HTTPException(400, "That bench is larger than we can store")
    ids = set()
    for c in body.candidates:
        if not isinstance(c.get("id"), int) or not isinstance(c.get("name"), str) \
                or not c["name"].strip() or c["id"] in ids:
            raise HTTPException(400, "Every candidate needs a unique id and a name")
        ids.add(c["id"])
    if n > had:
        assert_bench_room(user, n - 1)      # raises 402 if the last one doesn't fit
    if not doc:
        doc = BenchDoc(user_id=user.id)
        db.add(doc)
    doc.candidates = body.candidates
    doc.submissions = body.submissions
    db.commit()
    return _out(doc)
