# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""JWT verification against Supabase. Do not roll your own auth —
password reset and session rotation are where solo projects leak."""
import datetime as dt
from fastapi import Depends, HTTPException, Header
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from api.db import get_db
from api.models import User
from api.settings import settings


def current_user(authorization: str = Header(None),
                 db: Session = Depends(get_db)) -> User:
    # Dev mode: no Supabase configured yet? Sign in as a local demo user so you
    # can exercise every endpoint before wiring auth. Never active in prod.
    if settings.ENV == "dev" and not settings.SUPABASE_JWT_SECRET:
        return _dev_user(db)
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Not signed in")
    token = authorization.split(" ", 1)[1]
    try:
        claims = jwt.decode(token, settings.SUPABASE_JWT_SECRET,
                            algorithms=["HS256"], audience="authenticated")
    except JWTError as e:
        raise HTTPException(401, f"Invalid session: {e}")

    email = claims.get("email")
    if not email:
        raise HTTPException(401, "Token has no email claim")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, name=claims.get("user_metadata", {}).get("full_name"),
                    referral_code=_mk_code(email))
        db.add(user); db.commit(); db.refresh(user)

    user.last_active_at = dt.datetime.now(dt.timezone.utc)
    db.commit()
    return user


def optional_user(authorization: str = Header(None),
                  db: Session = Depends(get_db)):
    try: return current_user(authorization, db)
    except HTTPException: return None


def _dev_user(db: Session) -> User:
    u = db.query(User).filter(User.email == "dev@careerpilot.local").first()
    if not u:
        u = User(email="dev@careerpilot.local", name="Dev User", slug="dev",
                 plan="pro", work_auth=["h1b"], referral_code="devcode")
        db.add(u); db.commit(); db.refresh(u)
    return u


def _mk_code(email: str) -> str:
    import hashlib
    base = email.split("@")[0].lower()
    base = "".join(c for c in base if c.isalnum())[:18] or "user"
    return f"{base}{hashlib.sha256(email.encode()).hexdigest()[:4]}"
