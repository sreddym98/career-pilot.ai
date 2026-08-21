"""Sign-in and the seeker/recruiter split.

The point of these two account types is that they are enforced by the server,
not by which buttons the sidebar renders. So most of this file is about what
happens when a recruiter's token is pointed at a seeker endpoint anyway.
"""
import os, sys
os.environ.setdefault("DATABASE_URL", "sqlite:///./auth_test.db")
os.environ.setdefault("ENV", "dev")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

P = F = 0; fails = []
def ok(n, c, x=""):
    global P, F
    if c: P += 1
    else: F += 1; fails.append(f"{n}  →  {x}")

def raises(status, fn, *a, **k):
    """Returns (matched, detail) so a wrong status shows up in the failure."""
    from fastapi import HTTPException
    try:
        fn(*a, **k)
        return False, "no exception raised"
    except HTTPException as e:
        return e.status_code == status, f"got {e.status_code}: {e.detail}"

from api.db import init_db, SessionLocal
from api.models import User
from api import passwords, tokens
from api.auth import current_user
from api.access import require_seeker, require_recruiter, bench_limit
import api.routers.accounts as A
init_db()
db = SessionLocal()

for email in ("seeker@authtest.example.com", "recruiter@authtest.example.com", "dupe@authtest.example.com"):
    u = db.query(User).filter(User.email == email).first()
    if u: db.delete(u); db.commit()

print("\n╔═══ AUTH — two account types, enforced ═══╗\n")

print("── Passwords ──")
h = passwords.hash_password("correct-horse-battery")
ok("hash isn't the password", h != "correct-horse-battery")
ok("correct password verifies", passwords.verify("correct-horse-battery", h))
ok("wrong password doesn't", not passwords.verify("correct-horse-batter", h))
ok("no stored hash never matches", not passwords.verify("anything", None))
ok("same password hashes differently each time",
   passwords.hash_password("correct-horse-battery") != h, "salt isn't being applied")
m, d = raises(400, passwords.hash_password, "short")
ok("short password rejected", m, d)
# 72 bytes is bcrypt's ceiling; past it the tail is ignored rather than hashed.
m, d = raises(400, passwords.hash_password, "a" * 73)
ok("over-72-byte password rejected, not truncated", m, d)

print("\n── Signup ──")
s = A.signup(A.SignupIn(email="seeker@authtest.example.com", password="a-good-password",
                        name="Sam Seeker", account_type="seeker"), db)
r = A.signup(A.SignupIn(email="recruiter@authtest.example.com", password="a-good-password",
                        name="Rita Recruiter", account_type="recruiter"), db)
ok("signup returns a token", bool(s.get("access_token")))
ok("signup echoes the account type", s["user"]["account_type"] == "seeker", s["user"]["account_type"])
ok("recruiter signup sticks", r["user"]["account_type"] == "recruiter", r["user"]["account_type"])
ok("no password hash in the response", "password_hash" not in str(s["user"]))
ok("recruiter is told their bench cap", r["user"].get("bench_limit") == 3, r["user"].get("bench_limit"))
ok("seeker isn't shown a bench cap", "bench_limit" not in s["user"])
ok("signup is free — no plan required", r["user"]["plan"] == "free", r["user"]["plan"])

m, d = raises(409, A.signup, A.SignupIn(email="seeker@authtest.example.com",
              password="a-good-password", account_type="seeker"), db)
ok("duplicate email refused", m, d)
m, d = raises(400, A.signup, A.SignupIn(email="dupe@authtest.example.com",
              password="a-good-password", account_type="employer"), db)
ok("unknown account type refused", m, d)

print("\n── Login ──")
li = A.login(A.LoginIn(email="seeker@authtest.example.com", password="a-good-password"), db)
ok("correct credentials sign in", bool(li.get("access_token")))
ok("login reports the account type", li["user"]["account_type"] == "seeker")
m, d = raises(401, A.login, A.LoginIn(email="seeker@authtest.example.com", password="wrong"), db)
ok("wrong password rejected", m, d)
m1, _ = raises(401, A.login, A.LoginIn(email="nobody@authtest.example.com", password="wrong"), db)
ok("unknown email rejected", m1)
# Same wording either way, or the error message becomes a registered-user oracle.
try: A.login(A.LoginIn(email="seeker@authtest.example.com", password="wrong"), db)
except Exception as e1: msg_wrong = str(e1.detail)
try: A.login(A.LoginIn(email="nobody@authtest.example.com", password="wrong"), db)
except Exception as e2: msg_missing = str(e2.detail)
ok("  bad password and unknown email read identically",
   msg_wrong == msg_missing, f"{msg_wrong!r} vs {msg_missing!r}")

print("\n── Tokens ──")
seeker = db.query(User).filter(User.email == "seeker@authtest.example.com").first()
recruiter = db.query(User).filter(User.email == "recruiter@authtest.example.com").first()
claims = tokens.verify(li["access_token"])
ok("our own token verifies", claims is not None)
ok("  carries the user id", claims and claims.get("sub") == seeker.id)
ok("garbage token doesn't verify", tokens.verify("not.a.token") is None)
ok("token signed with another key doesn't verify",
   tokens.verify(li["access_token"][:-3] + "aaa") is None)

resolved = current_user(f"Bearer {li['access_token']}", db)
ok("a bearer token resolves to the right user", resolved.id == seeker.id)
m, d = raises(401, current_user, "Bearer tampered.token.here", db)
ok("an invalid bearer token is rejected, not waved through", m, d)

print("\n── Hard separation ──")
ok("seeker passes the seeker gate", require_seeker(seeker).id == seeker.id)
ok("recruiter passes the recruiter gate", require_recruiter(recruiter).id == recruiter.id)
m, d = raises(403, require_seeker, recruiter)
ok("recruiter is refused a seeker endpoint", m, d)
m, d = raises(403, require_recruiter, seeker)
ok("seeker is refused a recruiter endpoint", m, d)

# The whole reason authorization reads the row instead of the token: a session
# minted before an account change must not keep the access it was minted with.
stale = tokens.issue(recruiter)["access_token"]
recruiter.account_type = "seeker"; db.commit()
ok("a stale token can't outrank the database",
   require_seeker(current_user(f"Bearer {stale}", db)).id == recruiter.id)
recruiter.account_type = "recruiter"; db.commit()

print("\n── Bench cap ──")
from api.access import assert_bench_room
ok("free recruiter capped at 3", bench_limit(recruiter) == 3, bench_limit(recruiter))
recruiter.plan = "recruiter"; db.commit()
ok("paid recruiter lifted to 10", bench_limit(recruiter) == 10, bench_limit(recruiter))
ok("  room below the cap", assert_bench_room(recruiter, 9) is None)
m, d = raises(402, assert_bench_room, recruiter, 10)
ok("  402 at the cap, not 403 — it's a bill, not a permission", m, d)
recruiter.plan = "enterprise"; db.commit()
ok("enterprise uncapped", bench_limit(recruiter) is None)
ok("  no ceiling to hit", assert_bench_room(recruiter, 5000) is None)
recruiter.plan = "free"; db.commit()

print("\n── Session ──")
sess = A.session(seeker, db)
ok("session names the account type", sess["user"]["account_type"] == "seeker")
ok("session leaks no credential",
   not any(k in sess["user"] for k in ("password_hash", "access_token", "stripe_customer")))

print(f"\n{'─'*46}\nPASS {P}    FAIL {F}")
for f in fails: print("  ✗", f)
db.close()
sys.exit(1 if F else 0)
