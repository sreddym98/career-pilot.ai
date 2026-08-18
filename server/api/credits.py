# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Credit accounting. Referrals grant recurring monthly credits,
not a one-time bonus — that's what makes sharing worth doing."""
import datetime as dt
from sqlalchemy.orm import Session
from api.models import User, Referral
from api.settings import PLAN_CREDITS, REFERRAL_BONUS, CREDIT_CAP


def active_referrals(db: Session, user_id: str) -> int:
    return db.query(Referral).filter(
        Referral.referrer_id == user_id,
        Referral.status == "active").count()


def allowance(db: Session, user: User) -> int:
    base = PLAN_CREDITS.get(user.plan, PLAN_CREDITS["free"])
    bonus = active_referrals(db, user.id) * REFERRAL_BONUS
    return min(CREDIT_CAP, base + bonus)


def _aware(d):
    if d is None: return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def _roll_if_new_month(db: Session, user: User):
    now = dt.datetime.now(dt.timezone.utc)
    r = _aware(user.credits_reset_at)
    if r is None or (r.year, r.month) != (now.year, now.month):
        user.credits_used = 0
        user.credits_reset_at = now
        db.commit()


def remaining(db: Session, user: User) -> int:
    _roll_if_new_month(db, user)
    return max(0, allowance(db, user) - (user.credits_used or 0))


def spend(db: Session, user: User, n: int = 1):
    _roll_if_new_month(db, user)
    user.credits_used = (user.credits_used or 0) + n
    db.commit()


def qualify_pending(db: Session):
    """Cron: flip 'joined' referrals to 'active' once the referee has
    stuck around. Stops throwaway signups from farming credits."""
    from api.settings import REFERRAL_QUALIFY_DAYS
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=REFERRAL_QUALIFY_DAYS)
    pending = db.query(Referral).filter(Referral.status == "joined").all()
    n = 0
    for r in pending:
        referee = db.query(User).get(r.referee_id)
        if referee and _aware(referee.created_at) <= cutoff and _aware(referee.last_active_at) >= cutoff:
            r.status = "active"
            r.qualified_at = dt.datetime.now(dt.timezone.utc)
            n += 1
    db.commit()
    return n
