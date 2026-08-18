# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from api.db import get_db
from api.auth import current_user
from api.models import User, Referral
from api.settings import settings, REFERRAL_BONUS, CREDIT_CAP, PLAN_CREDITS
from api import credits

router = APIRouter(prefix="/api/referrals", tags=["referrals"])


@router.get("")
def my_referrals(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(Referral).filter(Referral.referrer_id == user.id)\
             .order_by(Referral.created_at.desc()).all()
    def mask(e):
        if not e or "@" not in e: return ""
        a, b = e.split("@", 1)
        return f"{a[0]}{'•' * 3}@{b}"
    out = []
    for r in rows:
        referee = db.query(User).get(r.referee_id) if r.referee_id else None
        out.append({"name": (referee.name if referee else None) or mask(r.email_invited),
                    "email_masked": mask(referee.email if referee else r.email_invited),
                    "status": r.status,
                    "credits": REFERRAL_BONUS if r.status == "active" else 0,
                    "created_at": r.created_at})
    active = sum(1 for r in rows if r.status == "active")
    return {"link": f"{settings.FRONTEND_URL}/join/{user.referral_code}",
            "sent": len(rows),
            "joined": sum(1 for r in rows if r.status != "invited"),
            "active": active,
            "bonus_credits": active * REFERRAL_BONUS,
            "allowance": credits.allowance(db, user),
            "cap": CREDIT_CAP,
            "base": PLAN_CREDITS.get(user.plan, 10),
            "referrals": out}


class Invite(BaseModel):
    emails: list[EmailStr]


@router.post("/invite")
def invite(body: Invite, user: User = Depends(current_user), db: Session = Depends(get_db)):
    made = 0
    for e in body.emails[:20]:
        if db.query(Referral).filter(Referral.referrer_id == user.id,
                                     Referral.email_invited == str(e)).first():
            continue
        db.add(Referral(referrer_id=user.id, email_invited=str(e)))
        made += 1
    db.commit()
    return {"invited": made}


@router.post("/attribute/{code}")
def attribute(code: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Called once on signup when the user arrived via /join/{code}."""
    if user.referred_by:
        raise HTTPException(400, "Already attributed")
    ref = db.query(User).filter(User.referral_code == code).first()
    if not ref or ref.id == user.id:
        raise HTTPException(400, "Invalid referral code")
    user.referred_by = ref.id
    existing = db.query(Referral).filter(Referral.referrer_id == ref.id,
                                         Referral.email_invited == user.email).first()
    if existing:
        existing.referee_id = user.id
        existing.status = "joined"
    else:
        db.add(Referral(referrer_id=ref.id, referee_id=user.id,
                        email_invited=user.email, status="joined"))
    db.commit()
    # Credits unlock only after REFERRAL_QUALIFY_DAYS — see credits.qualify_pending
    return {"attributed_to": ref.referral_code, "unlocks_in_days": 7}
