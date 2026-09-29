# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Authorization sweep, Gmail-not-configured behaviour, and account export/delete.

    DATABASE_URL=sqlite:///./ci_authz.db ENV=dev python3 test_authz.py

Three things this pins:
  1. Every route except the deliberately public ones refuses a bad credential
     (dev mode signs in *anonymous* callers, so a bad token is the honest probe).
  2. One user cannot read or change another user's rows through any id-bearing
     endpoint (applications, connections, positions, autopilot queue, evaluation).
  3. Gmail is never offered to Google unless it is fully configured, and the
     account export / delete endpoints touch only the caller.
"""
import os, sys, time, re
os.environ.setdefault("DATABASE_URL", "sqlite:///./ci_authz.db")
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
from api.models import (User, Application, Connection, Position, AutopilotConfig, Evaluation,
                        Integration, Referral)
from api.settings import settings, Settings
from api import ratelimit as RL, tokens
import api.routers.integrations as INT
import api.routers.accounts as ACC

init_db()
client = TestClient(app, raise_server_exceptions=False)
db = SessionLocal()
RL.reset()
RUN = str(int(time.time() * 1000))

def signup(tag, plan="free", kind="seeker"):
    r = client.post("/api/auth/signup", json={"email": f"{tag}{RUN}@authz.example.com", "password": "Correct-horse-9",
                                              "name": tag, "account_type": kind})
    assert r.status_code == 201, r.text
    d = r.json()
    if plan != "free":
        u = db.get(User, d["user"]["id"]); u.plan = plan; db.commit()
    return d["user"]["id"], {"Authorization": "Bearer " + d["access_token"]}

A_id, A = signup("alice", "pro")
B_id, B = signup("bob", "pro")

# ── 1. bad credential on every route ─────────────────────────────────────────
print("── every route rejects a bad token ──")
PUBLIC = {("GET", "/health"), ("GET", "/ready"), ("GET", "/api/jobs"), ("GET", "/api/jobs/{fingerprint}"),
          ("GET", "/api/u/{slug}"), ("POST", "/api/auth/signup"), ("POST", "/api/auth/login"),
          ("GET", "/api/billing/config"), ("POST", "/api/billing/webhook"),        # Stripe signature
          ("POST", "/api/autopilot/tick"),                                          # X-Cron-Secret
          ("POST", "/api/autopilot/diag"),                                          # X-Cron-Secret
          ("POST", "/api/autopilot/ingest"),                                        # X-Cron-Secret
          ("GET", "/api/integrations/gmail/callback"),                              # Google redirect; signed state
          ("GET", "/docs"), ("GET", "/docs/oauth2-redirect"), ("GET", "/openapi.json")}
BAD = {"Authorization": "Bearer not.a.token"}
swept = 0
for route in app.routes:
    methods = getattr(route, "methods", None)
    if not methods: continue
    for m in methods - {"HEAD", "OPTIONS"}:
        if (m, route.path) in PUBLIC: continue
        path = re.sub(r"\{[^}]+\}", "x", route.path)
        r = client.request(m, path, headers=BAD, json={} if m in ("POST", "PUT", "PATCH", "DELETE") else None)
        swept += 1
        ok(f"{m} {route.path} refuses a bad token", r.status_code == 401, r.status_code)
ok("sweep covered a meaningful number of routes", swept >= 40, swept)

# ── 2. IDOR: bob pokes at alice's ids ────────────────────────────────────────
print("── cross-user access ──")
app_row = Application(user_id=A_id, company="AliceCo", title="QA", status="submitted"); db.add(app_row)
con = Connection(user_id=A_id, name="Pal", company="AliceCo", degree=1); db.add(con)
pos = Position(user_id=A_id, company="AliceCo", role="QA", started_on=__import__("datetime").date(2020, 1, 1), bullets=["x"])
db.add(pos)
pos2 = Position(user_id=A_id, company="Old", role="QA", started_on=__import__("datetime").date(2018, 1, 1), bullets=["x"])
db.add(pos2)
ap = Application(user_id=A_id, company="AliceCo", title="Auto", status="ready", origin="autopilot"); db.add(ap)
ev = Evaluation(user_id=A_id, paid=True, report={"summary": "secret"}); db.add(ev)
db.commit()

def code(method, path, **kw):
    return client.request(method, path, headers=B, **kw).status_code

ok("PATCH another user's application -> 404", code("PATCH", f"/api/applications/{app_row.id}", json={"status": "rejected"}) == 404)
ok("DELETE another user's application -> 404", code("DELETE", f"/api/applications/{app_row.id}") == 404)
ok("PUT another user's connection -> 404", code("PUT", f"/api/connections/{con.id}", json={"name": "x", "company": "y"}) == 404)
ok("DELETE another user's connection -> 404", code("DELETE", f"/api/connections/{con.id}") == 404)
ok("PUT another user's position -> 404", code("PUT", f"/api/positions/{pos.id}",
   json={"company": "z", "role": "z", "started_on": "2020-01-01", "bullets": ["b"]}) == 404)
ok("GET autopilot queue item of another user -> 404", code("GET", f"/api/autopilot/queue/{ap.id}") == 404)
ok("approve another user's queue item -> 404", code("POST", f"/api/autopilot/queue/{ap.id}/approve") == 404)
ok("skip another user's queue item -> 404", code("DELETE", f"/api/autopilot/queue/{ap.id}") == 404)
ok("GET another user's evaluation -> 404", code("GET", f"/api/evaluation/{ev.id}") == 404)
ok("run another user's evaluation -> 404", code("POST", f"/api/evaluation/{ev.id}/run") == 404)
ok("set goals on another user's evaluation -> 404", code("POST", f"/api/evaluation/{ev.id}/goals", json={}) == 404)
# B bulk-approving must not touch A's queue
client.post("/api/autopilot/queue/approve-all", headers=B)
db.expire_all()
ok("approve-all only touches the caller's queue", db.get(Application, ap.id).status == "ready")
# B's lists never contain A's rows
ok("applications list is scoped", all(a["company"] != "AliceCo" for a in client.get("/api/applications", headers=B).json()["applications"]))
ok("connections list is scoped", client.get("/api/connections", headers=B).json()["total"] == 0)
ok("profile is the caller's", client.get("/api/profile", headers=B).json()["id"] == B_id)
ok("A's rows are unchanged after B's attempts", db.get(Application, app_row.id).status == "submitted"
   and db.get(Connection, con.id) is not None and db.get(Position, pos.id).company == "AliceCo")
# support admin queue hidden from non-admins (prod semantics: dev treats everyone as admin, so check the function)
from api.access import is_admin
_env = settings.ENV; settings.ENV = "prod"
ok("non-listed user is not admin in prod", not is_admin(db.get(User, B_id)))
settings.ENV = _env

# ── 3. Gmail: never send anyone to Google half-configured ────────────────────
print("── gmail configuration ──")
saved = {k: getattr(settings, k) for k in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REDIRECT_URI",
                                            "INTEGRATION_ENCRYPTION_KEY", "ENV", "AUTH_SECRET")}
def cfg(**kw):
    for k, v in {**saved, **kw}.items(): setattr(settings, k, v)
    # prod refuses the built-in dev signing key, but this test's tokens were
    # minted with it; pin it explicitly so ENV=prod can be exercised here.
    if settings.ENV != "dev" and not settings.AUTH_SECRET:
        settings.AUTH_SECRET = "dev-only-insecure-signing-key-do-not-use-in-production"
def start():
    RL.reset()
    return client.get("/api/integrations/gmail/start", headers=A)

cfg(GMAIL_CLIENT_ID="", GMAIL_CLIENT_SECRET="", INTEGRATION_ENCRYPTION_KEY="")
r = start()
ok("unset client id -> 503, no Google URL", r.status_code == 503 and "authorization_url" not in r.text and "accounts.google.com" not in r.text, r.text)
ok("status reports gmail not configured", client.get("/api/integrations/status", headers=A).json()["gmail"]["configured"] is False)

cfg(GMAIL_CLIENT_ID="id.apps.googleusercontent.com", GMAIL_CLIENT_SECRET="s", INTEGRATION_ENCRYPTION_KEY="k" * 40, GMAIL_REDIRECT_URI="")
ok("empty redirect uri -> 503", start().status_code == 503)
cfg(GMAIL_CLIENT_ID="id.apps.googleusercontent.com", GMAIL_CLIENT_SECRET="s", INTEGRATION_ENCRYPTION_KEY="k" * 40,
    GMAIL_REDIRECT_URI="http://localhost:8000/api/integrations/gmail/callback", ENV="prod")
_r = start(); ok("localhost redirect uri in prod -> 503 (the untouched default)", _r.status_code == 503, (_r.status_code, _r.text[:100]))
cfg(GMAIL_CLIENT_ID="id.apps.googleusercontent.com", GMAIL_CLIENT_SECRET="s", INTEGRATION_ENCRYPTION_KEY="k" * 40,
    GMAIL_REDIRECT_URI="http://api.example.com/cb", ENV="prod")
ok("http redirect uri in prod -> 503", start().status_code == 503)

good = "https://careerpilot-api-rri9.onrender.com/api/integrations/gmail/callback"
cfg(GMAIL_CLIENT_ID="id.apps.googleusercontent.com", GMAIL_CLIENT_SECRET="s", INTEGRATION_ENCRYPTION_KEY="k" * 40,
    GMAIL_REDIRECT_URI=good, ENV="dev")
r = start()
url = r.json().get("authorization_url", "")
from urllib.parse import urlparse, parse_qs
q = parse_qs(urlparse(url).query)
ok("fully configured -> Google URL", r.status_code == 200 and url.startswith("https://accounts.google.com/"), r.text)
ok("client_id and redirect_uri are what we configured", q.get("client_id") == ["id.apps.googleusercontent.com"]
   and q.get("redirect_uri") == [good], q)
ok("only the send scope + identity are requested", q.get("scope") == ["openid email https://www.googleapis.com/auth/gmail.send"], q.get("scope"))
state = q["state"][0]

print("── gmail callback ──")
def cb(**params):
    return client.get("/api/integrations/gmail/callback", params=params)
r = cb(error="access_denied", state=state)
ok("user pressing Deny -> friendly page, not a 422/JSON", r.status_code == 400 and "text/html" in r.headers["content-type"] and "not connected" in r.text, (r.status_code, r.text[:120]))
r = cb(code="c")
ok("missing state -> friendly page", r.status_code == 400 and "text/html" in r.headers["content-type"], r.status_code)
r = cb(code="c", state="garbage")
ok("forged state rejected", r.status_code == 400 and "text/html" in r.headers["content-type"], r.status_code)
tampered = state[:-4] + ("AAAA" if not state.endswith("AAAA") else "BBBB")
ok("tampered state rejected", cb(code="c", state=tampered).status_code == 400)
# expired state
real_time = time.time
time.time = lambda: real_time() + 601
ok("expired state rejected", cb(code="c", state=state).status_code == 400)
time.time = real_time
# state made for a user who no longer exists
ghost = INT._state_for("00000000-0000-0000-0000-000000000000")
ok("state for a deleted account rejected", cb(code="c", state=ghost).status_code == 400)
# happy path with Google mocked; token must be stored encrypted
class R:
    status_code = 200
    text = ""
    def json(self): return {"refresh_token": "1//refresh-token-value"}
INT.requests.post = lambda *a, **k: R()
r = cb(code="c", state=state)
row = db.query(Integration).filter(Integration.user_id == A_id, Integration.provider == "gmail").first()
ok("callback connects the STATE's user", r.status_code == 200 and row is not None and row.status == "connected", r.text[:120])
ok("refresh token is stored encrypted", row and "refresh-token-value" not in (row.credential or "")
   and INT._fernet().decrypt(row.credential.encode()).decode() == "1//refresh-token-value")
ok("other users are not connected", db.query(Integration).filter(Integration.user_id == B_id).count() == 0)
ok("status never exposes the credential", "credential" not in client.get("/api/integrations/status", headers=A).text)
cfg()

# ── 4. sessions for deleted accounts do not resurrect them ───────────────────
print("── export + delete ──")
C_id, C = signup("carol", "free")
exp = client.get("/api/auth/export", headers=C)
ok("export returns the caller's data", exp.status_code == 200 and exp.json()["account"]["id"] == C_id, exp.text[:120])
ok("export omits the password hash", "password_hash" not in exp.text and "$2b$" not in exp.text)
ok("export contains none of alice's rows", "AliceCo" not in exp.text)
ok("export of a user with a Gmail token omits the credential", "credential" not in client.get("/api/auth/export", headers=A).text)
ok("export needs a session", client.get("/api/auth/export", headers=BAD).status_code == 401)

ok("delete needs the confirm word", client.request("DELETE", "/api/auth/account", headers=C, json={"password": "Correct-horse-9", "confirm": "yes"}).status_code == 400)
ok("delete needs the right password", client.request("DELETE", "/api/auth/account", headers=C, json={"password": "wrong-password", "confirm": "DELETE"}).status_code == 401)
ok("account still exists after refused deletes", db.get(User, C_id) is not None)

# give carol data + a referral tie to alice, then delete her
db.add(Application(user_id=C_id, company="CarolCo", title="x", status="submitted"))
db.add(Referral(referrer_id=A_id, referee_id=C_id, email_invited="c@x.test", status="joined"))
cu = db.get(User, C_id); cu.referred_by = A_id; db.commit()
db.add(User(email=f"dave{RUN}@authz.example.com", referred_by=C_id, referral_code=f"dave{RUN}")); db.commit()
r = client.request("DELETE", "/api/auth/account", headers=C, json={"password": "Correct-horse-9", "confirm": "DELETE"})
db.expire_all()
ok("delete succeeds", r.status_code == 200 and r.json().get("deleted") is True, r.text)
ok("user row gone", db.get(User, C_id) is None)
ok("her applications gone", db.query(Application).filter(Application.user_id == C_id).count() == 0)
ok("someone she referred survives, un-attributed", db.query(User).filter(User.email == f"dave{RUN}@authz.example.com").first().referred_by is None)
ok("alice and her data are untouched", db.get(User, A_id) is not None and db.get(Application, app_row.id) is not None)
r = client.get("/api/auth/session", headers=C)
ok("the deleted user's old token no longer works (no silent re-creation)", r.status_code == 401, r.status_code)
ok("and did not recreate the account", db.query(User).filter(User.email == f"carol{RUN}@authz.example.com").count() == 0)

# ── 5. small config guards ───────────────────────────────────────────────────
print("── config ──")
ok("FRONTEND_URL trailing slash is stripped (CORS compares exactly)",
   Settings(FRONTEND_URL="https://career-pilot-ai.mamindlasreddy.workers.dev/").FRONTEND_URL
   == "https://career-pilot-ai.mamindlasreddy.workers.dev")

# interview generation is rate limited like the other AI endpoints
import api.routers.interview as IV
IV._call = lambda *a, **k: {"technical": []}
settings.RATE_AI_PER_USER = 2
RL.reset()
db.add(Position(user_id=B_id, company="BCo", role="QA", started_on=__import__("datetime").date(2021, 1, 1), bullets=["x"])); db.commit()
codes = [client.post("/api/interview/mock", headers=B, json={"job_title": f"QA {i}"}).status_code for i in range(4)]
ok("interview/mock is rate limited per user", codes[:2] == [200, 200] and 429 in codes[2:], codes)

print(f"\nPASS {P}    FAIL {F}")
if fails:
    print("\n".join("  ✗ " + f for f in fails)); sys.exit(1)
print("ALL GREEN")
