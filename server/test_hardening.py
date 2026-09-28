# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Hardening tests: rate limiter, security headers, health/ready, webhook
idempotency, body cap, 500 handler, support notification.

    DATABASE_URL=sqlite:///./ci_hardening.db ENV=dev python3 test_hardening.py
"""
import os, sys, json, time, types
os.environ.setdefault("DATABASE_URL", "sqlite:///./ci_hardening.db")
os.environ.setdefault("ENV", "dev")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RUN = str(int(time.time() * 1000))  # event ids must be unique per run: DB persists
P = F = 0
fails = []
def ok(name, cond, extra=""):
    global P, F
    if cond: P += 1
    else:
        F += 1; fails.append(f"{name}  ->  {extra}")

from fastapi.testclient import TestClient
from api.main import app
from api.db import init_db, SessionLocal
from api.models import User
from api.settings import settings
from api import ratelimit as RL, mailer
import api.routers.billing as B
import api.routers.support as SUP
import api.main as M

init_db()
client = TestClient(app, raise_server_exceptions=False)
db = SessionLocal()
RL.reset()

# ── limiter core ──
print("── limiter core ──")
clock = [1000.0]
RL._now = lambda: clock[0]
chk = [("k", 3, 60)]
ok("allows N", all(RL.hit(chk) == 0 for _ in range(3)))
w = RL.hit(chk)
ok("blocks N+1 with wait", w >= 1, w)
clock[0] += 61
ok("window reset allows again", RL.hit(chk) == 0)
clock[0] += 10
RL.hit(chk); RL.hit(chk)
w = RL.hit(chk)
ok("sliding: wait counts down from oldest hit", 1 <= w <= 51, w)
ok("blocked request not recorded", RL.hit([("k2", 1, 60), ("k", 3, 60)]) >= 1
   and RL.hit([("k2", 1, 60)]) == 0)
RL._now = time.monotonic
RL.reset()

# ── client IP / spoofing ──
print("── client IP ──")
def fake(xff, peer="10.0.0.1"):
    hdrs = {"x-forwarded-for": xff} if xff is not None else {}
    return types.SimpleNamespace(client=types.SimpleNamespace(host=peer), headers=hdrs)
ok("dev ignores X-Forwarded-For", RL.client_ip(fake("1.2.3.4")) == "10.0.0.1")
settings.ENV = "prod"
try:
    ok("prod uses first hop", RL.client_ip(fake("1.2.3.4, 9.9.9.9")) == "1.2.3.4")
    ok("garbage header falls back to peer", RL.client_ip(fake("not-an-ip")) == "10.0.0.1")
    ok("no header falls back to peer", RL.client_ip(fake(None)) == "10.0.0.1")
    settings.TRUSTED_IP_HOP = -1
    ok("hop -1 uses last entry", RL.client_ip(fake("6.6.6.6, 9.9.9.9")) == "9.9.9.9")
    settings.TRUSTED_IP_HOP = 0
    # Rotating a spoofed first hop must not dodge the per-email ceiling.
    RL.reset()
    settings.RATE_AUTH_PER_EMAIL = 4
    codes = []
    for i in range(6):
        r = client.post("/api/auth/login", json={"email": "victim@x.example", "password": "nope"},
                        headers={"X-Forwarded-For": f"8.8.8.{i}"})
        codes.append(r.status_code)
    ok("IP rotation doesn't bypass per-email limit", codes[:4] == [401] * 4 and codes[4:] == [429, 429], codes)
finally:
    settings.ENV = "dev"
    settings.RATE_AUTH_PER_EMAIL = 20
RL.reset()

# ── sign-in limits over HTTP ──
print("── sign-in / sign-up limits ──")
codes = [client.post("/api/auth/login", json={"email": "a@x.example", "password": "wrong"}).status_code
         for _ in range(10)]
ok("10 attempts pass through to auth (401)", codes == [401] * 10, codes)
r = client.post("/api/auth/login", json={"email": "a@x.example", "password": "wrong"})
ok("11th attempt is 429", r.status_code == 429, r.status_code)
ok("  with Retry-After", int(r.headers.get("retry-after", 0)) >= 1, r.headers)
ok("  and a plain message", "Too many requests" in r.json()["detail"], r.text)
r = client.post("/api/auth/login", json={"email": "b@x.example", "password": "wrong"})
ok("other email from same IP still allowed", r.status_code == 401, r.status_code)
r = client.post("/api/auth/signup", json={"email": "a@x.example", "password": "a-good-password"})
ok("signup shares the IP+email budget", r.status_code == 429, r.status_code)
RL.reset()
settings.RATE_AUTH_PER_IP = 3
codes = [client.post("/api/auth/login", json={"email": f"u{i}@x.example", "password": "w"}).status_code
         for i in range(4)]
ok("per-IP limit across different emails", codes == [401, 401, 401, 429], codes)
settings.RATE_AUTH_PER_IP = 30
RL.reset()
settings.RATE_LIMIT_ENABLED = False
codes = {client.post("/api/auth/login", json={"email": "c@x.example", "password": "w"}).status_code
         for _ in range(12)}
ok("RATE_LIMIT_ENABLED=false switches it off", codes == {401}, codes)
settings.RATE_LIMIT_ENABLED = True
RL.reset()

# ── password rules ──
print("── account checks ──")
r = client.post("/api/auth/signup", json={"email": "weak@x.example", "password": "password123"})
ok("common password rejected", r.status_code == 400, r.status_code)
r = client.post("/api/auth/login", json={"email": "weak@x.example", "password": "p" * 100})
ok(">72-byte login is a plain 401", r.status_code == 401, r.status_code)

# ── other limited endpoints ──
print("── phone / gmail / support / AI ──")
RL.reset()
codes = [client.post("/api/integrations/phone/start", json={"phone": "+15551234567"}).status_code
         for _ in range(4)]
ok("phone/start: 3 allowed, 4th is 429", codes[:3] != [429] * 3 and 429 not in codes[:3] and codes[3] == 429, codes)
RL.reset()
settings.RATE_GMAIL_START = 2
codes = [client.get("/api/integrations/gmail/start").status_code for _ in range(3)]
ok("gmail/start limited", codes[2] == 429 and 429 not in codes[:2], codes)
settings.RATE_GMAIL_START = 10
RL.reset()
settings.RATE_SUPPORT = 2
body = {"subject": "Something broke", "message": "It does not work at all, please help."}
codes = [client.post("/api/support", json=body).status_code for _ in range(3)]
ok("support submit limited", codes == [200, 200, 429], codes)
settings.RATE_SUPPORT = 5
RL.reset()
settings.RATE_AI_PER_USER = 2
codes = [client.get("/api/ai/credits").status_code for _ in range(3)]
ok("AI endpoints limited per user", codes[2] == 429 and codes[:2] == [200, 200], codes)
settings.RATE_AI_PER_USER = 30
RL.reset()

# ── security headers ──
print("── security headers ──")
r = client.get("/health")
ok("nosniff", r.headers.get("x-content-type-options") == "nosniff")
ok("referrer-policy", "referrer-policy" in r.headers)
ok("x-frame-options", r.headers.get("x-frame-options") == "DENY")
ok("no HSTS in dev", "strict-transport-security" not in r.headers)
settings.ENV = "prod"
r = client.get("/health")
ok("HSTS outside dev", "max-age" in r.headers.get("strict-transport-security", ""))
settings.ENV = "dev"
r = client.get("/api/ai/credits")
ok("API responses are no-store", r.headers.get("cache-control") == "no-store")

# ── health vs ready ──
print("── /health vs /ready ──")
class DeadEngine:
    def connect(self): raise RuntimeError("db down: postgres://user:secret@host/db")
real_engine = M.engine
M.engine = DeadEngine()
try:
    r = client.get("/health")
    ok("/health OK with the DB down (no DB touch)", r.status_code == 200 and r.json() == {"ok": True}, r.text)
    r = client.get("/ready")
    ok("/ready is 503 with the DB down", r.status_code == 503, r.status_code)
    ok("  and leaks nothing", "secret" not in r.text and "postgres" not in r.text, r.text)
finally:
    M.engine = real_engine
r = client.get("/ready")
ok("/ready 200 when the DB is up", r.status_code == 200 and r.json() == {"ok": True}, r.text)
ok("neither exposes ENV", "env" not in client.get("/health").text.lower() and "dev" not in r.text)

# ── global 500 handler ──
print("── error handler ──")
@app.get("/__boom")
def _boom(): raise RuntimeError("secret internals /home/x/db.py")
r = client.get("/__boom")
ok("unhandled error -> generic 500", r.status_code == 500 and r.json() == {"detail": "Internal server error"}, r.text)
ok("  no internals leaked", "secret" not in r.text)
ok("  still carries security headers", r.headers.get("x-content-type-options") == "nosniff")

# ── body cap ──
print("── body size cap ──")
big = "x" * (settings.MAX_BODY_BYTES + 10)
r = client.post("/api/auth/login", content=big, headers={"content-type": "application/json"})
ok("oversized body -> 413", r.status_code == 413, r.status_code)
def chunks():
    for _ in range(3): yield b"y" * (settings.MAX_BODY_BYTES // 2)
r = client.post("/api/auth/login", content=chunks(), headers={"content-type": "application/json"})
ok("oversized chunked body -> 413", r.status_code == 413, r.status_code)

# ── webhook: mocked Stripe, idempotency, unknown price ──
print("── webhook ──")
settings.STRIPE_WEBHOOK_SECRET = "whsec_mock"
B.PRICES = {"pro": "price_monthly_mock", "recruiter": "price_recruiter_mock"}
B.PRO_TERM_PRICES = {1: "price_monthly_mock", 3: "", 6: ""}
class MockWebhook:
    @staticmethod
    def construct_event(payload, sig, secret):
        if sig != "good": raise ValueError("Invalid signature")
        return json.loads(payload)
sub_price = {"id": "price_monthly_mock"}
class MockSub:
    @staticmethod
    def retrieve(sid): return {"items": {"data": [{"price": sub_price}]}}
B.stripe = types.SimpleNamespace(api_key="x", Webhook=MockWebhook, Subscription=MockSub)

u = db.query(User).filter(User.email == "hard@test.local").first()
if not u:
    u = User(email="hard@test.local", name="H", plan="free", stripe_customer="cus_H", referral_code="hardtest")
    db.add(u); db.commit()
u.plan = "free"; db.commit()

def post(event, sig="good"):
    return client.post("/api/billing/webhook", content=json.dumps(event),
                       headers={"stripe-signature": sig, "content-type": "application/json"})
def plan():
    db.expire_all(); return db.query(User).filter(User.email == "hard@test.local").first().plan

ev = {"id": f"evt_1_{RUN}", "type": "checkout.session.completed",
      "data": {"object": {"client_reference_id": u.id, "subscription": "sub_1"}}}
r = post(ev)
ok("first delivery processed", r.status_code == 200 and not r.json().get("duplicate") and plan() == "pro", (r.text, plan()))
u2 = db.query(User).get(u.id); u2.plan = "free"; db.commit()
r = post(ev)
ok("duplicate event id ignored", r.json().get("duplicate") is True and plan() == "free", (r.text, plan()))
r = post({**ev, "id": f"evt_2_{RUN}"})
ok("a different event id is processed", plan() == "pro", plan())
r = post(ev, sig="bad")
ok("bad signature still rejected", r.status_code == 400, r.status_code)
big_ev = json.dumps({"id": f"evt_big_{RUN}", "type": "x", "data": {"object": {}}, "pad": "z" * (settings.MAX_BODY_BYTES + 100)})
r = client.post("/api/billing/webhook", content=big_ev, headers={"stripe-signature": "good"})
ok("webhook not blocked by the 1 MB API cap", r.status_code != 413, r.status_code)

u2 = db.query(User).get(u.id); u2.plan = "free"; db.commit()
sub_price["id"] = "price_unknown_xyz"
post({"id": f"evt_3_{RUN}", "type": "checkout.session.completed",
      "data": {"object": {"client_reference_id": u.id, "subscription": "sub_2"}}})
ok("unknown price on checkout does not grant Pro", plan() == "free", plan())
post({"id": f"evt_4_{RUN}", "type": "customer.subscription.updated",
      "data": {"object": {"customer": "cus_H", "status": "active",
                          "items": {"data": [{"price": {"id": "price_unknown_xyz"}}]}}}})
ok("unknown price on update does not grant Pro", plan() == "free", plan())
post({"id": f"evt_5_{RUN}", "type": "customer.subscription.updated",
      "data": {"object": {"customer": "cus_H", "status": "incomplete",
                          "items": {"data": [{"price": {"id": "price_monthly_mock"}}]}}}})
ok("incomplete subscription does not grant Pro", plan() == "free", plan())
post({"id": f"evt_6_{RUN}", "type": "customer.subscription.updated",
      "data": {"object": {"customer": "cus_H", "status": "active",
                          "items": {"data": [{"price": {"id": "price_recruiter_mock"}}]}}}})
ok("known recruiter price maps to recruiter", plan() == "recruiter", plan())

# ── support notification ──
print("── support email ──")
sent = []
real_send = mailer.send
mailer.send = lambda to, subject, text: sent.append((to, subject, text)) or True
def wait_for(n):
    for _ in range(100):
        if len(sent) >= n: return
        time.sleep(0.02)
T = SUP.TicketIn(subject="Help\nBcc: evil", message="Something is wrong with my account.")
u3 = db.query(User).get(u.id); u3.plan = "pro"; db.commit()
try:
    settings.SUPPORT_EMAIL = ""
    SUP.submit_ticket(T, u3, db); time.sleep(0.1)
    ok("empty SUPPORT_EMAIL sends nothing", sent == [], sent)
    settings.SUPPORT_EMAIL = "support@example.test"
    SUP.submit_ticket(T, u3, db); wait_for(1)
    ok("paid plan emailed with PRIORITY in the subject",
       len(sent) == 1 and sent[0][0] == "support@example.test" and "[PRIORITY]" in sent[0][1], sent)
    ok("  subject can't inject headers", "\n" not in sent[0][1], sent[0][1])
    u3.plan = "free"; db.commit()
    SUP.submit_ticket(T, u3, db); wait_for(2)
    ok("free plan is not marked priority", len(sent) == 2 and "[PRIORITY]" not in sent[1][1], sent)
    def boom(*a, **k): raise RuntimeError("smtp down")
    mailer.send = boom
    r = SUP.submit_ticket(T, u3, db); time.sleep(0.1)
    ok("mail failure never fails the ticket", bool(r["id"]))
finally:
    mailer.send = real_send
    settings.SUPPORT_EMAIL = ""

print("\n" + "=" * 48)
print(f"PASS {P}    FAIL {F}")
if F:
    print("\nFAILURES")
    for f in fails: print("  x " + f)
    raise SystemExit(1)
print("ALL GREEN")
