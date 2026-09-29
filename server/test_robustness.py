# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Regression tests for bugs found in backend QA. Run on SQLite and Postgres:

    DATABASE_URL=sqlite:///./ci_robust.db ENV=dev python3 test_robustness.py
    DATABASE_URL=postgresql://... ENV=dev python3 test_robustness.py

Covers: malformed path ids must 404 (Postgres used to 500 with a uuid
DataError), negative paging is a 422, non-ASCII secrets/OAuth state are
rejected instead of raising TypeError, and UUID/ARRAY/JSONB columns round-trip.
"""
import os, sys, base64, uuid
os.environ.setdefault("DATABASE_URL", "sqlite:///./ci_robust.db")
os.environ.setdefault("ENV", "dev")
os.environ["CRON_SECRET"] = "cron-secret-x"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

P = F = 0; fails = []
def ok(n, c, x=""):
    global P, F
    if c: P += 1
    else: F += 1; fails.append(f"{n}  ->  {x}")

from fastapi.testclient import TestClient
from fastapi import HTTPException
from api.main import app
from api.db import init_db, SessionLocal
from api.models import User, AutopilotConfig, Evaluation
from api.settings import settings
from api.routers import integrations as INT
settings.RATE_LIMIT_ENABLED = False
settings.CRON_SECRET = "cron-secret-x"
init_db()
c = TestClient(app, raise_server_exceptions=False)
sfx = uuid.uuid4().hex[:8]
r = c.post("/api/auth/signup", json={"email": f"rb{sfx}@robust.example.com", "password": "Str0ng!pass9-x"})
ok("signup", r.status_code in (200, 201), r.text)
H = {"Authorization": "Bearer " + r.json()["access_token"]}

print("── malformed ids 404, never 500 ──")
for m, p, body in [
    ("PATCH", "/api/applications/not-a-uuid", {"status": "submitted"}),
    ("DELETE", "/api/applications/not-a-uuid", None),
    ("PUT", "/api/connections/not-a-uuid", {"name": "a", "company": "b"}),
    ("DELETE", "/api/connections/not-a-uuid", None),
    ("GET", "/api/evaluation/not-a-uuid", None),
    ("POST", "/api/evaluation/not-a-uuid/goals", {}),
    ("POST", "/api/evaluation/not-a-uuid/run", None),
    ("GET", "/api/autopilot/queue/not-a-uuid", None),
    ("POST", "/api/autopilot/queue/not-a-uuid/approve", None),
    ("DELETE", "/api/autopilot/queue/not-a-uuid", None),
    ("PUT", "/api/positions/not-a-uuid", {"company": "a", "role": "b", "started_on": "2020-01-01", "bullets": ["x"]}),
]:
    r = c.request(m, p, headers=H, json=body) if body is not None else c.request(m, p, headers=H)
    ok(f"{m} {p} -> 404", r.status_code == 404, r.status_code)

print("── paging bounds ──")
ok("limit=-1 is 422", c.get("/api/jobs?limit=-1").status_code == 422)
ok("limit=0 is 422", c.get("/api/jobs?limit=0").status_code == 422)
ok("offset=-1 is 422", c.get("/api/jobs?offset=-1").status_code == 422)
ok("normal paging 200", c.get("/api/jobs?limit=5&offset=0").status_code == 200)

print("── non-ASCII secrets are rejected, not a 500 ──")
r = c.post("/api/autopilot/tick", headers={"x-cron-secret": "crön".encode("latin-1")})
ok("tick non-ascii secret -> 401", r.status_code == 401, r.status_code)
ok("tick right secret -> 202", c.post("/api/autopilot/tick", headers={"x-cron-secret": "cron-secret-x"}).status_code == 202)
settings.INTEGRATION_ENCRYPTION_KEY = "k" * 32
db = SessionLocal()
def state(sig, issued="1"):
    return base64.urlsafe_b64encode(f"uid:{issued}:nonce:{sig}".encode()).decode()
for name, s in [("non-ascii signature", state("sé")), ("non-numeric issued", state("abc", "xx")), ("garbage", "!!!")]:
    try: INT._user_from_state(s, db); ok(f"state {name}", False, "no exception")
    except HTTPException as e: ok(f"state {name} -> 400", e.status_code == 400, e.status_code)
    except Exception as e: ok(f"state {name} -> 400", False, repr(e))

print("── UUID / ARRAY / JSONB round trip ──")
u = User(email=f"rt{sfx}@robust.example.com"); db.add(u); db.commit()
db.add(AutopilotConfig(user_id=u.id, on=False, resume_confirmed=False, slots=[9, 13], titles=["a", "b"], skills=[], work_style="")); db.commit(); db.expire_all()
cfg = db.get(AutopilotConfig, u.id)
ok("uuid pk is str", isinstance(u.id, str) and len(u.id) == 36)
ok("int-array round trip", list(cfg.slots) == [9, 13], cfg.slots)
ok("str-array round trip", list(cfg.titles) == ["a", "b"] and list(cfg.skills) == [], (cfg.titles, cfg.skills))
ok("db.get with junk id is None, not an error", db.get(User, "junk") is None)

print("── concurrent skill saves never 500 (duplicate-key race seen in production) ──")
import threading as _th
_codes = []
def _put():
    _codes.append(c.put("/api/profile/skills", headers=H,
                        json={"skills": ["Playwright", "Cypress", "Java"], "top": ["Java"]}).status_code)
_ts = [_th.Thread(target=_put) for _ in range(10)]
[t.start() for t in _ts]; [t.join() for t in _ts]
ok("10 simultaneous saves all succeed", _codes.count(200) == 10, _codes)
ok("no duplicate rows afterwards",
   sorted(c.get("/api/profile", headers=H).json()["skills"]) == ["Cypress", "Java", "Playwright"])

print("\n" + "=" * 48); print(f"PASS {P}    FAIL {F}")
if F:
    print("\nFAILURES"); [print("  x", f) for f in fails]; sys.exit(1)
print("ALL GREEN")
