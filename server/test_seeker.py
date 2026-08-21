"""The "For me" side: profile, skills, applications, connections.

Everything a job seeker types should survive a different browser. Before this,
most of it lived in localStorage and the backend models sat unused — so these
tests are mostly about persistence actually happening, and about a recruiter
account being unable to reach any of it.
"""
import os, sys
os.environ.setdefault("DATABASE_URL", "sqlite:///./seeker_test.db")
os.environ.setdefault("ENV", "dev")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

P = F = 0; fails = []
def ok(n, c, x=""):
    global P, F
    if c: P += 1
    else: F += 1; fails.append(f"{n}  →  {x}")

def raises(status, fn, *a, **k):
    from fastapi import HTTPException
    try:
        fn(*a, **k); return False, "no exception raised"
    except HTTPException as e:
        return e.status_code == status, f"got {e.status_code}: {e.detail}"

from api.db import init_db, SessionLocal
from api.models import User, Position, UserSkill, Application, Connection, Job
import api.routers.profile as PR
import api.routers.applications as AP
import api.routers.connections as CN
import api.routers.accounts as AC
init_db()
db = SessionLocal()

for e in ("sk@seekertest.example.com", "rc@seekertest.example.com"):
    u = db.query(User).filter(User.email == e).first()
    if u: db.delete(u); db.commit()

seeker = db.query(User).filter(User.id == AC.signup(AC.SignupIn(
    email="sk@seekertest.example.com", password="a-good-password",
    name="Sam Seeker", account_type="seeker"), db)["user"]["id"]).first()
recruiter = db.query(User).filter(User.id == AC.signup(AC.SignupIn(
    email="rc@seekertest.example.com", password="a-good-password",
    name="Rita", account_type="recruiter"), db)["user"]["id"]).first()

print("\n╔═══ FOR ME — the seeker side persists ═══╗\n")

print("── Profile ──")
p = PR.update_profile(PR.ProfileIn(headline="Senior SDET", location="St. Louis, MO",
                                   phone="+1 919-555-0100", linkedin="linkedin.com/in/sam",
                                   summary="Eight years in test automation.",
                                   work_auth=["h1b"]), seeker, db)
ok("headline saved", p["headline"] == "Senior SDET", p["headline"])
ok("location saved", p["location"] == "St. Louis, MO")
ok("phone saved", p["phone"] == "+1 919-555-0100")
ok("linkedin saved", p["linkedin"] == "linkedin.com/in/sam")
ok("work auth saved", p["work_auth"] == ["h1b"], p["work_auth"])
ok("name untouched by a partial save", p["name"] == "Sam Seeker", p["name"])

# The bug this guards: sending only one card's fields must not blank the rest.
p = PR.update_profile(PR.ProfileIn(location="Dallas, TX"), seeker, db)
ok("a partial update leaves other fields alone",
   p["headline"] == "Senior SDET" and p["phone"] == "+1 919-555-0100", p["headline"])
ok("  and applies the one field sent", p["location"] == "Dallas, TX")

p = PR.update_profile(PR.ProfileIn(headline=""), seeker, db)
ok("an empty string clears a field (it's a real edit)", p["headline"] == "", repr(p["headline"]))
m, d = raises(400, PR.update_profile, PR.ProfileIn(name="   "), seeker, db)
ok("but the name can't be blanked", m, d)
m, d = raises(400, PR.update_profile, PR.ProfileIn(work_auth=["martian"]), seeker, db)
ok("unknown work authorization refused", m, d)

print("\n── Public address (slug) ──")
p = PR.update_profile(PR.ProfileIn(slug="Sam Reddy!"), seeker, db)
ok("slug is normalised, not trusted", p["slug"] == "sam-reddy", p["slug"])
m, d = raises(409, PR.update_profile, PR.ProfileIn(slug="api"), seeker, db)
ok("reserved slugs refused", m, d)
m, d = raises(400, PR.update_profile, PR.ProfileIn(slug="ab"), seeker, db)
ok("too-short slug refused", m, d)
PR.update_profile(PR.ProfileIn(slug="rita-page"), recruiter, db) if False else None
other = User(email="taken@seekertest.example.com", name="T", slug="taken-one", referral_code="tk1")
db.add(other); db.commit()
m, d = raises(409, PR.update_profile, PR.ProfileIn(slug="taken-one"), seeker, db)
ok("someone else's slug refused", m, d)
ok("  public page resolves by slug", PR.public_profile("sam-reddy", db)["name"] == "Sam Seeker")

print("\n── Skills ──")
r = PR.replace_skills(PR.SkillsIn(skills=["Playwright", "Java", "playwright", " SQL "],
                                  top=["Playwright"]), seeker, db)
ok("duplicates collapsed case-insensitively", r["skills"] == ["Playwright", "Java", "SQL"], r["skills"])
ok("whitespace trimmed", "SQL" in r["skills"])
ok("top skills marked", r["top"] == ["Playwright"], r["top"])
ok("  persisted as a flag", db.query(UserSkill).filter(
    UserSkill.user_id == seeker.id, UserSkill.is_top == True).count() == 1)
r = PR.replace_skills(PR.SkillsIn(skills=["Cypress"]), seeker, db)
ok("replacing really replaces", r["skills"] == ["Cypress"], r["skills"])
ok("  old rows gone", db.query(UserSkill).filter(UserSkill.user_id == seeker.id).count() == 1)
m, d = raises(400, PR.replace_skills, PR.SkillsIn(skills=[f"s{i}" for i in range(61)]), seeker, db)
ok("absurd skill lists refused", m, d)

print("\n── Applications ──")
a1 = AP.track(AP.ApplicationIn(company="Vaspire", title="Senior SDET",
                               location="Minneapolis, MN", status="sent"), seeker, db)
ok("tracked", a1["company"] == "Vaspire")
ok("  short code accepted", a1["status"] == "submitted", a1["status"])
ok("  and echoed back", a1["short"] == "sent", a1["short"])
ok("  applied_at stamped once submitted", a1["applied_at"] is not None)

a2 = AP.track(AP.ApplicationIn(company="vaspire", title="senior sdet", status="intv"), seeker, db)
ok("same posting upserts rather than duplicating", a2["id"] == a1["id"])
ok("  status advanced", a2["short"] == "intv", a2["short"])
ok("  one row, not two", db.query(Application).filter(
    Application.user_id == seeker.id).count() == 1, db.query(Application).filter(
    Application.user_id == seeker.id).count())

AP.track(AP.ApplicationIn(company="Bank of America", title="Quality Engineer",
                          status="closed", blocker="sponsorship"), seeker, db)
lst = AP.list_applications(None, seeker, db)
ok("both listed", lst["total"] == 2, lst["total"])
ok("  counted by stage", lst["counts"] == {"intv": 1, "closed": 1}, lst["counts"])
ok("  blocker kept", any(a["blocker"] == "sponsorship" for a in lst["applications"]))
ok("filtering by stage works", AP.list_applications("closed", seeker, db)["total"] == 1)

up = AP.set_status(a1["id"], AP.StatusIn(status="offer", note="Offer today"), seeker, db)
ok("status patched", up["short"] == "offer", up["short"])
ok("  note kept", up["note"] == "Offer today")
m, d = raises(400, AP.track, AP.ApplicationIn(company="X", title="Y", status="banana"), seeker, db)
ok("unknown status refused", m, d)
m, d = raises(400, AP.track, AP.ApplicationIn(company="  ", title="Y"), seeker, db)
ok("blank company refused", m, d)

# A posting found on LinkedIn has no row in our jobs table. It must still track.
ext = AP.track(AP.ApplicationIn(company="Elsewhere Inc", title="SDET",
                                fingerprint="not-a-real-fingerprint"), seeker, db)
ok("an outside posting still tracks", ext["id"] is not None)
ok("  without inventing a job link", ext["fingerprint"] is None, ext["fingerprint"])

ok("deleting works", AP.untrack(a1["id"], seeker, db)["deleted"])
ok("  and it's gone", AP.list_applications(None, seeker, db)["total"] == 2,
   AP.list_applications(None, seeker, db)["total"])
m, d = raises(404, AP.untrack, a1["id"], seeker, db)
ok("deleting twice is a 404", m, d)

print("\n── Board states the tracker actually uses ──")
# mark() calls these from six places (opening a job, skipping one, Autopilot
# approval). They were rejected with a 400 the client swallowed, so every one
# of those transitions silently failed to persist.
for short in ("opened", "skipped"):
    a = AP.track(AP.ApplicationIn(company=f"Co-{short}", title="SDET", status=short), seeker, db)
    ok(f"'{short}' is accepted", a["status"] == short, a["status"])
    ok(f"  and round-trips unchanged", a["short"] == short, a["short"])
    ok(f"  without claiming you applied", a["applied_at"] is None, a["applied_at"])

# A re-mark usually carries only the new status. It must not blank the rest.
full = AP.track(AP.ApplicationIn(company="Keeper", title="QA", location="Austin, TX",
                                 note="Referred by Anil", status="sent"), seeker, db)
thin = AP.track(AP.ApplicationIn(company="Keeper", title="QA", status="intv"), seeker, db)
ok("a partial re-mark keeps the note", thin["note"] == "Referred by Anil", thin["note"])
ok("  keeps the location", thin["location"] == "Austin, TX", thin["location"])
ok("  and still advances the status", thin["short"] == "intv", thin["short"])
ok("  same row", thin["id"] == full["id"])

print("\n── Connections ──")
c1 = CN.add_connection(CN.ConnectionIn(name="Anil Kumar", company="Cognizant",
                                       role="Senior QA", degree=1,
                                       how_known="Worked together at TCS"), seeker, db)
CN.add_connection(CN.ConnectionIn(name="Meera S", company="Cognizant", degree=2), seeker, db)
CN.add_connection(CN.ConnectionIn(name="Deepa Nair", company="UnitedHealth", degree=1), seeker, db)
lst = CN.list_connections(seeker, db)
ok("all three kept", lst["total"] == 3, lst["total"])
ok("grouped by employer", len(lst["companies"]) == 2, len(lst["companies"]))
ok("  biggest group intact",
   len([c for c in lst["companies"] if c["company"] == "Cognizant"][0]["people"]) == 2)
m, d = raises(409, CN.add_connection, CN.ConnectionIn(name="anil kumar", company="cognizant"), seeker, db)
ok("the same person twice is refused", m, d)

db.add(Job(fingerprint="fp-cog-1", source="t", company="Cognizant", title="SDET", active=True))
db.commit()
lst = CN.list_connections(seeker, db)
cog = [c for c in lst["companies"] if c["company"] == "Cognizant"][0]
ok("open roles counted where you know someone", cog["open_roles"] == 1, cog["open_roles"])
# SQL groups by the raw column, so a case-variant company arrives as a second
# row. It has to add, not overwrite.
db.add(Job(fingerprint="fp-cog-2", source="t", company="cognizant", title="QA", active=True))
db.commit()
lst = CN.list_connections(seeker, db)
cog = [c for c in lst["companies"] if c["company"] == "Cognizant"][0]
ok("  case-variant company rows are summed, not overwritten",
   cog["open_roles"] == 2, cog["open_roles"])

CN.edit_connection(c1["id"], CN.ConnectionIn(name="Anil Kumar", company="Cognizant",
                                             role="QA Manager", degree=1), seeker, db)
ok("editing sticks", db.get(Connection, c1["id"]).role == "QA Manager")
ok("removing works", CN.remove_connection(c1["id"], seeker, db)["deleted"])
m, d = raises(404, CN.remove_connection, c1["id"], seeker, db)
ok("  removing twice is a 404", m, d)

print("\n── None of it belongs to a recruiter ──")
# Over HTTP, not by calling the handlers. Depends(require_seeker) is resolved
# by FastAPI at request time, so a direct Python call passes straight through
# the gate and would prove nothing at all.
from fastapi.testclient import TestClient
from api.main import app
from api import tokens
client = TestClient(app)
rtok = {"Authorization": "Bearer " + tokens.issue(recruiter)["access_token"]}
stok = {"Authorization": "Bearer " + tokens.issue(seeker)["access_token"]}

BLOCKED = [
    ("PUT",    "/api/profile",       {"headline": "x"}),
    ("PUT",    "/api/profile/skills",{"skills": ["x"]}),
    ("GET",    "/api/profile",       None),
    ("GET",    "/api/applications",  None),
    ("POST",   "/api/applications",  {"company": "A", "title": "B"}),
    ("GET",    "/api/connections",   None),
    ("POST",   "/api/connections",   {"name": "A", "company": "B"}),
]
for method, path, payload in BLOCKED:
    r = client.request(method, path, headers=rtok, json=payload)
    ok(f"recruiter refused {method} {path}", r.status_code == 403,
       f"got {r.status_code}: {r.text[:70]}")

for method, path, payload in BLOCKED:
    r = client.request(method, path, headers=stok, json=payload)
    ok(f"  seeker allowed {method} {path}", r.status_code < 400,
       f"got {r.status_code}: {r.text[:70]}")

# With no credential, ENV=dev signs you in as the local demo user. That is the
# documented convenience — and it must be impossible anywhere else, or the
# whole authorization story above is decoration.
from api.settings import settings as _s
from api.auth import current_user as _cu
r = client.get("/api/applications")
ok("dev with no credential falls back to the demo user", r.status_code == 200, r.status_code)
_was = _s.ENV
try:
    _s.ENV = "production"
    m, d = raises(401, _cu, None, db)
    ok("  but that fallback is dev-only — prod demands a credential", m, d)
    m, d = raises(401, _cu, "Bearer garbage", db)
    ok("  and prod rejects a junk token", m, d)
finally:
    _s.ENV = _was

print("\n── One seeker can't see another's ──")
other_seeker = db.query(User).filter(User.id == AC.signup(AC.SignupIn(
    email="other@seekertest.example.com", password="a-good-password",
    account_type="seeker"), db)["user"]["id"]).first()
ok("a fresh account starts empty", AP.list_applications(None, other_seeker, db)["total"] == 0)
ok("  and sees no one else's contacts", CN.list_connections(other_seeker, db)["total"] == 0)
m, d = raises(404, AP.untrack, lst["companies"][0]["people"][0]["id"], other_seeker, db)
ok("  can't delete across accounts", m, d)

print(f"\n{'─'*46}\nPASS {P}    FAIL {F}")
for f in fails: print("  ✗", f)
db.close()
sys.exit(1 if F else 0)
