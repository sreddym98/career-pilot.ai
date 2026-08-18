# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Billing tests with a mocked Stripe — no network, no real charges.

    python test_billing.py

Proves the webhook actually flips plans, that unsigned webhooks are
rejected, and that a missing config gives a clear error instead of a 500.
"""
import os, sys, json, types
os.environ.setdefault("DATABASE_URL", "sqlite:///./billing_test.db")
os.environ.setdefault("ENV", "dev")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

P = F = 0
fails = []
def ok(name, cond, extra=""):
    global P, F
    if cond: P += 1
    else:
        F += 1
        fails.append(f"{name}  →  {extra}")

from api.db import init_db, SessionLocal
from api.models import User
import api.settings as S

init_db()
db = SessionLocal()

u = db.query(User).filter(User.email == "billing@test.local").first()
if not u:
    u = User(email="billing@test.local", name="Billing Test", plan="free",
             stripe_customer="cus_TEST123", referral_code="billtest")
    db.add(u); db.commit(); db.refresh(u)
else:
    u.plan = "free"; u.stripe_customer = "cus_TEST123"; db.commit()

# ── mock stripe ──
import api.routers.billing as B
S.settings.STRIPE_SECRET_KEY = "sk_test_mock"
S.settings.STRIPE_PRICE_PRO_MONTHLY = "price_monthly_mock"
S.settings.STRIPE_PRICE_RECRUITER = "price_recruiter_mock"
S.settings.STRIPE_WEBHOOK_SECRET = "whsec_mock"
B.PRICES = {"pro": "price_monthly_mock", "recruiter": "price_recruiter_mock"}
B.PRO_TERM_PRICES = {1: "price_monthly_mock", 3: "price_3mo_mock", 6: "price_6mo_mock"}

class MockWebhook:
    verified = True
    @staticmethod
    def construct_event(payload, sig, secret):
        if not MockWebhook.verified:
            raise ValueError("Invalid signature")
        return json.loads(payload)

class MockSub:
    @staticmethod
    def retrieve(sid):
        return {"items": {"data": [{"price": {"id": "price_monthly_mock"}}]}}

B.stripe = types.SimpleNamespace(
    api_key="sk_test_mock",
    Webhook=MockWebhook,
    Subscription=MockSub,
    Customer=types.SimpleNamespace(create=lambda **k: types.SimpleNamespace(id="cus_NEW")),
    checkout=types.SimpleNamespace(Session=types.SimpleNamespace(
        create=lambda **k: types.SimpleNamespace(url="https://checkout.stripe.com/mock"))),
    billing_portal=types.SimpleNamespace(Session=types.SimpleNamespace(
        create=lambda **k: types.SimpleNamespace(url="https://billing.stripe.com/mock"))),
)

import asyncio
class Req:
    def __init__(self, body, sig="t=1,v1=mock"):
        self._b = json.dumps(body).encode(); self.headers = {"stripe-signature": sig}
    async def body(self): return self._b

def fire(event):
    return asyncio.run(B.webhook(Req(event), db))

print("\n╔═══ BILLING — mocked Stripe, real database ═══╗\n")

print("── config endpoint ──")
cfg = B.config()
ok("reports configured", cfg["configured"] is True)
ok("exposes publishable key only", "publishable_key" in cfg and "secret" not in json.dumps(cfg).lower())
ok("plan prices correct", cfg["plans"]["pro"]["amount"] == 11999 and cfg["plans"]["recruiter"]["amount"] == 16999)

print("── checkout ──")
r = B.checkout("pro", u, db)
ok("returns a checkout url", r["url"].startswith("https://checkout.stripe.com"))
try:
    B.checkout("nonsense", u, db); ok("rejects unknown plan", False)
except Exception as e:
    ok("rejects unknown plan", "Unknown plan" in str(e))

print("── webhook: upgrade ──")
fire({"type": "checkout.session.completed",
      "data": {"object": {"client_reference_id": u.id, "subscription": "sub_123"}}})
db.refresh(u)
ok("free → pro on payment", u.plan == "pro", u.plan)
ok("subscription id stored", u.stripe_subscription == "sub_123", u.stripe_subscription)

print("── webhook: recruiter ──")
MockSub.retrieve = staticmethod(lambda sid: {"items": {"data": [{"price": {"id": "price_recruiter_mock"}}]}})
u.plan = "free"; db.commit()
fire({"type": "checkout.session.completed",
      "data": {"object": {"client_reference_id": u.id, "subscription": "sub_456"}}})
db.refresh(u)
ok("recruiter price → recruiter plan", u.plan == "recruiter", u.plan)

print("── webhook: cancel ──")
fire({"type": "customer.subscription.deleted",
      "data": {"object": {"customer": "cus_TEST123", "status": "canceled",
                          "items": {"data": [{"price": {"id": "price_monthly_mock"}}]}}}})
db.refresh(u)
ok("cancel → free", u.plan == "free", u.plan)

print("── webhook: failed payment does NOT downgrade ──")
u.plan = "pro"; db.commit()
fire({"type": "invoice.payment_failed", "data": {"object": {"customer": "cus_TEST123"}}})
db.refresh(u)
ok("stays pro during retry window", u.plan == "pro", u.plan)

print("── webhook: unknown event doesn't crash ──")
res = fire({"type": "some.future.event", "data": {"object": {}}})
ok("unknown event acknowledged", res == {"received": True})

print("── SECURITY: signature verification ──")
MockWebhook.verified = False
u.plan = "free"; db.commit()
try:
    fire({"type": "checkout.session.completed",
          "data": {"object": {"client_reference_id": u.id, "subscription": "sub_FORGED"}}})
    ok("forged webhook REJECTED", False, "it was accepted")
except Exception as e:
    ok("forged webhook REJECTED", "signature" in str(e).lower() or "400" in str(e))
db.refresh(u)
ok("forged webhook did not upgrade", u.plan == "free", u.plan)
MockWebhook.verified = True

print("── missing config gives a clear error ──")
saved = S.settings.STRIPE_PRICE_PRO_MONTHLY
S.settings.STRIPE_PRICE_PRO_MONTHLY = ""
try:
    B.checkout("pro", u, db); ok("unconfigured → clear 503", False)
except Exception as e:
    ok("unconfigured → clear 503", "setup_stripe.py" in str(e), str(e)[:70])
S.settings.STRIPE_PRICE_PRO_MONTHLY = saved

saved_w = S.settings.STRIPE_WEBHOOK_SECRET
S.settings.STRIPE_WEBHOOK_SECRET = ""
try:
    fire({"type": "x", "data": {"object": {}}}); ok("no webhook secret → 503", False)
except Exception as e:
    ok("no webhook secret → 503", "stripe listen" in str(e), str(e)[:70])
S.settings.STRIPE_WEBHOOK_SECRET = saved_w


print("── term-based checkout ──")
S.settings.STRIPE_PRICE_PRO_3MO = "price_3mo_mock"
S.settings.STRIPE_PRICE_PRO_6MO = "price_6mo_mock"
_captured_price = {}
_orig_session_create = B.stripe.checkout.Session.create
def _capture_session_create(**k):
    _captured_price["price"] = k["line_items"][0]["price"]
    return types.SimpleNamespace(url="https://checkout.stripe.com/mock")
B.stripe.checkout.Session.create = _capture_session_create

r_term3 = B.checkout(plan="pro", term=3, user=u, db=db)
ok("3-month term uses the 3-month price id", _captured_price["price"] == "price_3mo_mock")

r_term6 = B.checkout(plan="pro", term=6, user=u, db=db)
ok("6-month term uses the 6-month price id", _captured_price["price"] == "price_6mo_mock")

r_term1 = B.checkout(plan="pro", term=1, user=u, db=db)
ok("default term=1 uses the monthly price id", _captured_price["price"] == "price_monthly_mock")

try:
    B.checkout(plan="pro", term=2, user=u, db=db)
    ok("invalid term (2) rejected", False)
except Exception as e:
    ok("invalid term (2) rejected", "400" in str(e))

B.stripe.checkout.Session.create = _orig_session_create
B.PRO_TERM_PRICES[6] = ""   # simulate the 6-month price not being set up yet
try:
    B.checkout(plan="pro", term=6, user=u, db=db)
    ok("unconfigured term price gives a clear error, not a crash", False)
except Exception as e:
    ok("unconfigured term price gives a clear error, not a crash", "503" in str(e) and "setup_stripe" in str(e))

print("\n" + "=" * 50)
print(f"PASS {P}    FAIL {F}")
if F:
    print("\nFAILURES"); [print("  ✗ " + f) for f in fails]
else:
    print("✓ ALL GREEN")
db.close()
os.path.exists("billing_test.db") and os.remove("billing_test.db")
