# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Who is making this request.

Accepts sessions from more than one issuer, tried in order:

  1. Supabase — active as soon as SUPABASE_JWT_SECRET is set.
  2. careerpilot — our own email+password sign-in (api/tokens.py).
  3. The dev user — local convenience only, and only when no credential was
     presented at all.

The ordering is what makes moving to a hosted provider a config change rather
than a rewrite: point signup at Supabase or Firebase, and sessions issued by
either side keep working while existing ones age out.
"""
import datetime as dt
from fastapi import Depends, HTTPException, Header
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from api.db import get_db
from api.models import User
from api.settings import settings, DEFAULT_ACCOUNT_TYPE
from api import tokens


def current_user(authorization: str = Header(None),
                 db: Session = Depends(get_db)) -> User:
    token = _bearer(authorization)

    if not token:
        # No credential. Locally that means "you haven't wired up sign-in yet",
        # and signing in as a demo user beats a 401 wall in front of every
        # endpoint. Anywhere else it means exactly what it says.
        if settings.ENV == "dev":
            return _dev_user(db)
        raise HTTPException(401, "Not signed in")

    hosted = _supabase_claims(token)
    claims = hosted or tokens.verify(token)
    if not claims:
        raise HTTPException(401, "Invalid or expired session")
    if not hosted and claims.get("scope"):
        # A scoped key (the browser extension's) is not a session. It only
        # works on the endpoints that ask for extension_or_user below.
        raise HTTPException(401, "This key only works in the CareerPilot extension")

    email = claims.get("email")
    if not email:
        raise HTTPException(401, "Token has no email claim")

    user = db.query(User).filter(User.email == email).first()
    if not user and not hosted:
        # A token WE issued for an account that no longer exists (deleted, or a
        # wiped database). It must not quietly mint a fresh account: after an
        # account deletion the old 7-day token would resurrect the user.
        raise HTTPException(401, "Invalid or expired session")
    if not user:
        # First sight of a hosted-provider account. Our own signup path always
        # creates the row itself, so it never lands here.
        meta = claims.get("user_metadata") or {}
        user = User(email=email, name=meta.get("full_name"),
                    account_type=_valid_type(meta.get("account_type")),
                    referral_code=_mk_code(email))
        db.add(user); db.commit(); db.refresh(user)

    user.last_active_at = dt.datetime.now(dt.timezone.utc)
    db.commit()
    return user


def extension_or_user(authorization: str = Header(None),
                      db: Session = Depends(get_db)) -> User:
    """A normal session, or the extension's scoped key (revocable, checked
    against extension_tokens on every request). Only the apply packet, the
    tailored-resume download and the fill/applied report use this."""
    token = _bearer(authorization)
    claims = tokens.verify(token) if token else None
    if claims and claims.get("scope") == tokens.EXTENSION_SCOPE:
        from api.models import ExtensionToken
        row = db.get(ExtensionToken, claims.get("jti") or "")
        if not row or row.revoked_at is not None or row.user_id != claims.get("sub"):
            raise HTTPException(401, "This extension key was disconnected. Connect the extension again.")
        user = db.get(User, row.user_id)
        if not user:
            raise HTTPException(401, "Invalid or expired session")
        row.last_used_at = dt.datetime.now(dt.timezone.utc)
        db.commit()
        return user
    return current_user(authorization, db)


def optional_user(authorization: str = Header(None),
                  db: Session = Depends(get_db)):
    try: return current_user(authorization, db)
    except HTTPException: return None


def _bearer(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization.split(" ", 1)[1].strip() or None


def _supabase_claims(token: str) -> dict | None:
    if not settings.SUPABASE_JWT_SECRET:
        return None
    try:
        return jwt.decode(token, settings.SUPABASE_JWT_SECRET,
                          algorithms=["HS256"], audience="authenticated")
    except JWTError:
        return None


def _valid_type(v) -> str:
    from api.settings import ACCOUNT_TYPES
    return v if v in ACCOUNT_TYPES else DEFAULT_ACCOUNT_TYPE


def _dev_user(db: Session) -> User:
    u = db.query(User).filter(User.email == "dev@careerpilot.local").first()
    if not u:
        u = User(email="dev@careerpilot.local", name="Dev User", slug="dev",
                 account_type="seeker", plan="pro", work_auth=["h1b"],
                 referral_code="devcode")
        db.add(u); db.commit(); db.refresh(u)
    return u


def _mk_code(email: str) -> str:
    import hashlib
    base = email.split("@")[0].lower()
    base = "".join(c for c in base if c.isalnum())[:18] or "user"
    return f"{base}{hashlib.sha256(email.encode()).hexdigest()[:4]}"
