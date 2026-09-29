"""Referral attribution and the People-I-Know endpoints the web app relies on.
The invite link only means something if signing up through it is recorded for
the sender, and if a person can't attribute themselves or be counted twice."""
import os, sys
os.path.exists("referrals_test.db") and os.remove("referrals_test.db")   # start clean
os.environ.setdefault("DATABASE_URL", "sqlite:///./referrals_test.db")
os.environ.setdefault("ENV", "dev")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

P = F = 0; fails = []
def ok(n, c, x=""):
    global P, F
    if c: P += 1
    else: F += 1; fails.append(f"{n}  →  {x}")

from fastapi import HTTPException
from api.db import init_db, SessionLocal
from api.models import User
import api.routers.referrals as R
import api.routers.connections as C
init_db()
db = SessionLocal()

def mk_user(email, code):
    u = db.query(User).filter(User.email == email).first()
    if not u:
        u = User(email=email, name=email.split("@")[0], plan="free", referral_code=code)
        db.add(u); db.commit(); db.refresh(u)
    return u

def raises(fn, status):
    try: fn(); return False
    except HTTPException as e: return e.status_code == status

print("\n╔═══ REFERRALS — the invite link counts for the sender ═══╗\n")
ana = mk_user("ana@ref.local", "ANA123")
bo = mk_user("bo@ref.local", "BO4567")

print("── A fresh account has nothing invented ──")
r = R.my_referrals(ana, db)
ok("no referrals to start", r["referrals"] == [] and r["sent"] == 0 and r["active"] == 0, r)
ok("link is built from the account's own code", r["link"].endswith("/join/ANA123"), r["link"])

print("── Signing up through the link is attributed ──")
out = R.attribute("ANA123", bo, db)
ok("attributed to the sender", out["attributed_to"] == "ANA123", out)
r = R.my_referrals(ana, db)
ok("sender now sees one person who joined", r["sent"] == 1 and r["joined"] == 1 and len(r["referrals"]) == 1, r)
ok("  who is not yet earning credits (7-day wait)", r["active"] == 0 and r["bonus_credits"] == 0)
ok("  and whose email is masked", r["referrals"][0]["email_masked"].startswith("b•••@"), r["referrals"][0])

print("── It cannot be gamed ──")
ok("second attribution for the same person is refused", raises(lambda: R.attribute("ANA123", bo, db), 400))
ok("own code is refused", raises(lambda: R.attribute("ANA123", ana, db), 400))
cy = mk_user("cy@ref.local", "CY8901")
ok("unknown code is refused", raises(lambda: R.attribute("NOPE", cy, db), 400))
ok("  and leaves the account unattributed", db.get(User, cy.id).referred_by is None)

print("── People I know starts empty and is per-account ──")
class In:
    def __init__(self, **k): self.__dict__.update({"role": None, "degree": 1, "how_known": None, **k})
ok("nothing listed for a new seeker", C.list_connections(ana, db)["total"] == 0)
row = C.add_connection(In(name="Ravi Kumar", company="Acme", role="QA Lead", how_known="Worked together"), ana, db)
ok("added", row["name"] == "Ravi Kumar" and row["company"] == "Acme")
ok("listed under the company", C.list_connections(ana, db)["companies"][0]["people"][0]["name"] == "Ravi Kumar")
ok("duplicate refused", raises(lambda: C.add_connection(In(name="ravi kumar", company="ACME"), ana, db), 409))
ok("another account sees none of it", C.list_connections(bo, db)["total"] == 0)
ok("another account cannot delete it", raises(lambda: C.remove_connection(row["id"], bo, db), 404))
ok("owner can delete it", C.remove_connection(row["id"], ana, db)["deleted"] is True)
ok("and it is gone", C.list_connections(ana, db)["total"] == 0)

print("\n" + "=" * 50)
print(f"PASS {P}    FAIL {F}")
if F: print("\nFAILURES"); [print("  ✗ " + f) for f in fails]
else: print("✓ ALL GREEN")
db.close()
os.path.exists("referrals_test.db") and os.remove("referrals_test.db")
sys.exit(1 if F else 0)
