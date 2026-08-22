# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Password hashing.

bcrypt directly rather than through passlib — one less dependency, and
passlib's bcrypt backend has a long-running version-detection break against
bcrypt 4.x that produces a warning on every single hash.
"""
import bcrypt
from fastapi import HTTPException

MIN_LENGTH = 8
# bcrypt hashes at most 72 bytes and SILENTLY IGNORES the rest. A 100-character
# passphrase would then match on its first 72 bytes alone, which is not what
# anyone typing it believes is happening. Reject instead of truncating.
MAX_BYTES = 72

# Hash of a password nobody holds. Compared against on unknown-email logins so
# a missing account costs the same ~250ms as a wrong password — otherwise the
# response time alone tells an attacker which emails are registered.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt())


def validate(password: str) -> None:
    """Raise if this password can't be safely stored or is trivially weak."""
    if len(password) < MIN_LENGTH:
        raise HTTPException(400, f"Password must be at least {MIN_LENGTH} characters")
    if len(password.encode("utf-8")) > MAX_BYTES:
        raise HTTPException(400, "Password is too long (72 bytes maximum)")


def hash_password(password: str) -> str:
    validate(password)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify(password: str, hashed: str | None) -> bool:
    """Check a password. Always does the full bcrypt work, even when there is
    no hash to check against, so timing stays flat across every failure mode."""
    if not hashed:
        bcrypt.checkpw(password.encode("utf-8")[:MAX_BYTES], _DUMMY_HASH)
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # Malformed hash in the row — treat as no match rather than a 500.
        return False
