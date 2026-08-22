# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Account-type authorization.

Seeker and recruiter are separate products. Hiding a nav item is presentation;
this module is the part that actually decides, and it reads account_type off
the User row rather than the session token so a stale token can never outrank
the database.

Attach at the router, not the endpoint — one line that can't be forgotten when
someone adds the next handler:

    router = APIRouter(prefix="/api/bench", dependencies=[Depends(require_recruiter)])
"""
from fastapi import Depends, HTTPException
from api.auth import current_user
from api.models import User
from api.settings import BENCH_LIMITS


def _require(kind: str, other: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.account_type != kind:
            raise HTTPException(403, f"This is a {kind} feature. "
                                     f"Your account is set up as a {other}.")
        return user
    return dep


require_seeker = _require("seeker", "recruiter")
require_recruiter = _require("recruiter", "seeker")


def bench_limit(user: User) -> int | None:
    """How many people this recruiter may keep on their bench. None = no cap.

    Signing up as a recruiter is free and always has been — the cap is what the
    paid plan lifts, so the product can be judged on a real bench before anyone
    is asked for a card.
    """
    return BENCH_LIMITS.get(user.plan, BENCH_LIMITS["free"])


def assert_bench_room(user: User, current_count: int) -> None:
    """Guard for whatever creates a candidate. 402 rather than 403 — nothing is
    wrong with the request, there is just a bill between it and success."""
    cap = bench_limit(user)
    if cap is not None and current_count >= cap:
        raise HTTPException(402, f"Your plan covers {cap} people on the bench. "
                                 f"Upgrade to add more.")
