# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Sessions we issue ourselves.

Deliberately a single long-lived access token with no refresh rotation. That
is the honest tradeoff for email+password sign-in on a demo build: refresh
rotation without server-side revocation buys almost nothing, and half-built
rotation is worse than none. When a hosted provider (Supabase, Firebase) takes
over sign-in, that provider brings real rotation with it and this module stops
being the primary path — see api/auth.py, which already accepts both.
"""
import datetime as dt
from jose import jwt, JWTError
from api.settings import settings, auth_secret

ALGORITHM = "HS256"
ISSUER = "careerpilot"


def issue(user) -> dict:
    """Mint a session for this user. Returns the token plus what the client
    needs to know about it, so the frontend never has to decode a JWT."""
    now = dt.datetime.now(dt.timezone.utc)
    expires = now + dt.timedelta(days=settings.AUTH_TOKEN_DAYS)
    claims = {
        "sub": user.id,
        "email": user.email,
        # Mirrored into the token for debugging only. Authorization always
        # re-reads account_type from the database — see api/access.py. A token
        # minted before a support-initiated account change must not out-rank
        # the row it describes.
        "account_type": user.account_type,
        "iss": ISSUER,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    return {
        "access_token": jwt.encode(claims, auth_secret(), algorithm=ALGORITHM),
        "token_type": "bearer",
        "expires_at": expires.isoformat(),
    }


def verify(token: str) -> dict | None:
    """Decode a careerpilot-issued token. None if it isn't one, or isn't valid.

    Returning None rather than raising is what lets api/auth.py try each
    configured issuer in turn without exception juggling.
    """
    try:
        return jwt.decode(token, auth_secret(), algorithms=[ALGORITHM],
                          issuer=ISSUER, options={"verify_aud": False})
    except (JWTError, RuntimeError):
        return None
