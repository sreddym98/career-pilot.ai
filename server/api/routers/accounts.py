# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Sign up, sign in, and "who am I".

There is no endpoint to change account_type, and that is on purpose. Seeker and
recruiter are different products sharing a job feed; a flag flip would leave a
recruiter's bench attached to an account the rest of the system now treats as a
job seeker. Someone who genuinely needs both keeps two accounts.
"""
import datetime as dt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from api.db import get_db
from api.auth import current_user, _mk_code
from api.access import bench_limit
from api.models import User
from api.settings import ACCOUNT_TYPES, DEFAULT_ACCOUNT_TYPE, settings
from api import passwords, tokens, credits
from api.ratelimit import auth_limit

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)
    name: str = Field("", max_length=100)
    account_type: str = DEFAULT_ACCOUNT_TYPE


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


# Passwords everyone tries first. Length alone (8) lets these through.
_COMMON = {"password", "password1", "password123", "12345678", "123456789",
           "1234567890", "qwerty123", "qwertyuiop", "iloveyou1", "11111111",
           "00000000", "abc12345", "letmein123", "welcome123"}


@router.post("/signup", status_code=201, dependencies=[Depends(auth_limit)])
def signup(body: SignupIn, db: Session = Depends(get_db)):
    if body.account_type not in ACCOUNT_TYPES:
        raise HTTPException(400, f"account_type must be one of {', '.join(ACCOUNT_TYPES)}")

    email = str(body.email).strip().lower()
    if db.query(User).filter(User.email == email).first():
        # Signup is the one place enumeration can't be designed away — the user
        # has to be told the address is taken. Login stays uniform; see below.
        raise HTTPException(409, "An account with that email already exists")

    if body.password.lower() in _COMMON or body.password.lower() == email:
        raise HTTPException(400, "That password is too easy to guess. Choose another.")

    user = User(email=email,
                name=(body.name or "").strip() or email.split("@")[0],
                account_type=body.account_type,
                password_hash=passwords.hash_password(body.password),
                referral_code=_mk_code(email))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Two signups for one address raced past the check above.
        db.rollback()
        raise HTTPException(409, "An account with that email already exists")
    db.refresh(user)
    return {**tokens.issue(user), "user": _summary(db, user)}


@router.post("/login", dependencies=[Depends(auth_limit)])
def login(body: LoginIn, db: Session = Depends(get_db)):
    email = str(body.email).strip().lower()
    user = db.query(User).filter(User.email == email).first()

    # One message and one code for every failure — wrong password, no such
    # account, provider-only account with no password set. Anything more
    # specific hands out a list of who is registered.
    pw_hash = user.password_hash if user else None
    if len(body.password.encode("utf-8")) > passwords.MAX_BYTES:
        # Can never match a stored hash (signup caps at 72 bytes). Burn the same
        # bcrypt time as any other failure so length doesn't reveal whether the
        # account exists.
        pw_hash = None
    if not passwords.verify(body.password, pw_hash):
        raise HTTPException(401, "That email and password don't match")

    user.last_active_at = dt.datetime.now(dt.timezone.utc)
    db.commit()
    return {**tokens.issue(user), "user": _summary(db, user)}


@router.get("/session")
def session(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Canonical "who am I". The frontend calls this on boot to decide which
    product to render — it must never infer that from a decoded token."""
    return {"user": _summary(db, user)}


@router.post("/logout")
def logout(user: User = Depends(current_user)):
    """Sessions are stateless, so this is the client dropping its token. It
    exists so the frontend has one honest thing to call, and so revocation has
    somewhere to live the day it's added."""
    return {"ok": True}


def _summary(db: Session, user: User) -> dict:
    """Everything the client needs to render the right product for this account
    and nothing it doesn't. No password hash, no Stripe ids, no tokens."""
    out = {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "account_type": user.account_type,
        "plan": user.plan,
        "slug": user.slug,
        "referral_code": user.referral_code,
        "credits_remaining": credits.remaining(db, user),
        "credits_allowance": credits.allowance(db, user),
    }
    if user.account_type == "recruiter":
        out["bench_limit"] = bench_limit(user)
    return out
