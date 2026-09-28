# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Recruiter bench persistence, the plan cap, and isolation between recruiters.

    DATABASE_URL=sqlite:///./ci_bench.db ENV=dev python3 test_bench.py
"""
import os, sys, time
os.environ.setdefault("DATABASE_URL", "sqlite:///./ci_bench.db")
os.environ.setdefault("ENV", "dev")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

P = F = 0; fails = []
def ok(n, c, x=""):
    global P, F
    if c: P += 1
    else: F += 1; fails.append(f"{n}  ->  {x}")

from fastapi.testclient import TestClient
from api.main import app
from api.db import init_db, SessionLocal
from api.models import User
from api import ratelimit as RL

init_db()
client = TestClient(app, raise_server_exceptions=False)
db = SessionLocal()
RL.reset()
RUN = str(int(time.time() * 1000))

def signup(tag, kind="recruiter", plan="free"):
    r = client.post("/api/auth/signup", json={"email": f"{tag}{RUN}@bench.example.com", "password": "Correct-horse-9",
                                              "name": tag, "account_type": kind})
    assert r.status_code == 201, r.text
    d = r.json()
    if plan != "free":
        u = db.get(User, d["user"]["id"]); u.plan = plan; db.commit()
    return {"Authorization": "Bearer " + d["access_token"]}

def cands(n, start=1):
    return [{"id": i, "name": f"Person {i}", "skills": ["SQL"], "avail": "now"} for i in range(start, start + n)]

def put(h, n, subs=None, start=1):
    return client.put("/api/bench", headers=h, json={"candidates": cands(n, start), "submissions": subs or []})

print("\n╔═══ BENCH — persisted, capped, private ═══╗\n")
A = signup("rita"); B = signup("rob"); S = signup("sam", kind="seeker")

print("── persistence ──")
r = client.get("/api/bench", headers=A).json()
ok("new recruiter has no bench doc yet", r == {"exists": False, "candidates": [], "submissions": []}, r)
r = put(A, 2, subs=[{"candId": 1, "jobId": "x", "st": "sent"}])
ok("save returns 200", r.status_code == 200, r.text)
r = client.get("/api/bench", headers=A).json()
ok("read back candidates", [c["name"] for c in r["candidates"]] == ["Person 1", "Person 2"], r)
ok("read back submissions", r["submissions"] == [{"candId": 1, "jobId": "x", "st": "sent"}], r)
ok("exists flag set", r["exists"] is True)
r = client.put("/api/bench", headers=A, json={"candidates": []}).json()
ok("emptying the bench is allowed and remembered", r["exists"] and r["candidates"] == [], r)

print("── plan cap (free = 3, recruiter = 10) ──")
ok("free: 3 fits", put(A, 3).status_code == 200)
r = put(A, 4)
ok("free: 4th person is 402", r.status_code == 402, (r.status_code, r.text))
ok("  message names the cap", "3" in r.json()["detail"], r.text)
ok("  rejected save did not change the bench", len(client.get("/api/bench", headers=A).json()["candidates"]) == 3)
ok("free: editing at the cap is fine", client.put("/api/bench", headers=A, json={
    "candidates": [{**c, "name": c["name"] + "!"} for c in cands(3)]}).status_code == 200)
ok("free: adding 5 at once is 402", put(A, 5).status_code == 402)
uid = db.query(User).filter(User.email == f"rita{RUN}@bench.example.com").first().id
u = db.get(User, uid); u.plan = "recruiter"; db.commit()
ok("recruiter plan: 10 fits", put(A, 10).status_code == 200)
ok("recruiter plan: 11 is 402", put(A, 11).status_code == 402)
u.plan = "free"; db.commit()
ok("downgraded over-cap bench can still shrink", put(A, 7).status_code == 200)
ok("  but not grow", put(A, 8).status_code == 402)
u.plan = "enterprise"; db.commit()
ok("enterprise: no cap", put(A, 40).status_code == 200)

print("── validation ──")
ok("candidate without a name is 400", client.put("/api/bench", headers=B, json={"candidates": [{"id": 1, "name": " "}]}).status_code == 400)
ok("duplicate ids are 400", client.put("/api/bench", headers=B, json={"candidates": [{"id": 1, "name": "a"}, {"id": 1, "name": "b"}]}).status_code == 400)
ok("non-integer id is 400", client.put("/api/bench", headers=B, json={"candidates": [{"id": "1", "name": "a"}]}).status_code == 400)

print("── isolation ──")
put(B, 1, start=100)
ra = client.get("/api/bench", headers=A).json()["candidates"]
rb = client.get("/api/bench", headers=B).json()["candidates"]
ok("A does not see B's people", all(c["id"] < 100 for c in ra), ra[:2])
ok("B sees only their own", [c["id"] for c in rb] == [100], rb)
ok("seeker gets 403", client.get("/api/bench", headers=S).status_code == 403)
ok("seeker cannot write either", put(S, 1).status_code == 403)
ok("no credential is 401", client.get("/api/bench", headers={"Authorization": "Bearer nope"}).status_code == 401)

print("── account deletion ──")
r = client.request("DELETE", "/api/auth/account", headers=B, json={"password": "Correct-horse-9", "confirm": "DELETE"})
ok("delete account succeeds with a bench", r.status_code == 200, r.text)
from api.models import BenchDoc
ok("bench row went with the account", db.query(BenchDoc).filter(BenchDoc.candidates != None).count() >= 1 and
   not any(d.user_id not in {x[0] for x in db.query(User.id).all()} for d in db.query(BenchDoc).all()))

print(f"\nPASS {P}    FAIL {F}")
if fails:
    print("\n".join("  ✗ " + f for f in fails)); sys.exit(1)
print("ALL GREEN")
