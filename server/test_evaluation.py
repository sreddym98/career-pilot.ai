# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Evaluation payment gate and report generation. No network, no real charges."""
import os, sys, json, types
os.environ.setdefault("DATABASE_URL", "sqlite:///./eval_test.db")
os.environ.setdefault("ENV", "dev")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

P = F = 0; fails = []
def ok(n, c, x=""):
    global P, F
    if c: P += 1
    else: F += 1; fails.append(f"{n}  →  {x}")

from api.db import init_db, SessionLocal
from api.models import User, Position, Evaluation
import api.settings as S
init_db()
db = SessionLocal()

u = db.query(User).filter(User.email == "eval@test.local").first()
if not u:
    u = User(email="eval@test.local", name="Eval Test", plan="free",
             work_auth=["h1b"], referral_code="evaltest")
    db.add(u); db.commit(); db.refresh(u)
if not db.query(Position).filter(Position.user_id == u.id).count():
    import datetime as dt
    db.add(Position(user_id=u.id, company="Acme", role="QA Engineer",
                    started_on=dt.date(2020,1,1), bullets=["Built test automation"]))
    db.commit()

import api.routers.evaluation as EV
import api.routers.billing as B
S.settings.STRIPE_SECRET_KEY = "sk_test_mock"
S.settings.STRIPE_PRICE_EVAL = "price_eval_mock"
S.settings.STRIPE_WEBHOOK_SECRET = "whsec_mock"

class MockWebhook:
    @staticmethod
    def construct_event(payload, sig, secret):
        return json.loads(payload)
_SESSION_N = {"n": 0}
def _mk_session(**k):
    _SESSION_N["n"] += 1
    return types.SimpleNamespace(url="https://checkout.stripe.com/eval", id=f"cs_E{_SESSION_N['n']}")
B.stripe = types.SimpleNamespace(
    api_key="sk_test_mock", Webhook=MockWebhook,
    Customer=types.SimpleNamespace(create=lambda **k: types.SimpleNamespace(id="cus_E1")),
    checkout=types.SimpleNamespace(Session=types.SimpleNamespace(create=_mk_session)),
)

import asyncio
class Req:
    def __init__(self, body):
        self._b = json.dumps(body).encode(); self.headers = {"stripe-signature": "t=1,v1=x"}
    async def body(self): return self._b
def fire(event): return asyncio.run(B.webhook(Req(event), db))

print("\n╔═══ EVALUATION — payment gate ═══╗\n")

print("── checkout ──")
r = B.checkout_evaluation(u, db)
ok("returns a checkout url", r["url"].startswith("https://checkout.stripe.com"))
eval_id = r["evaluation_id"]
ev = db.query(Evaluation).get(eval_id)
ok("evaluation row created unpaid", ev is not None and ev.paid is False)
ok("session id stored", ev.stripe_session_id == "cs_E1", ev.stripe_session_id)

print("── THE GATE: unpaid cannot get a report ──")
try:
    EV.run_evaluation(eval_id, u, db)
    ok("unpaid run() blocked", False, "it ran without payment")
except Exception as e:
    ok("unpaid run() blocked", "402" in str(e) or "haven't" in str(e).lower(), str(e)[:80])

print("── goals before payment ──")
class G:
    def model_dump(self):
        return {"target_title":"Senior SDET","target_industries":["fintech"],
                "timeline":"1-3 months","relocation":"open","priorities":["visa sponsorship","growth"],"notes":""}
EV.set_goals(eval_id, G(), u, db)
db.refresh(ev)
ok("goals saved pre-payment", ev.report and ev.report.get("_goals",{}).get("target_title")=="Senior SDET")

print("── webhook confirms payment ──")
fire({"type":"checkout.session.completed",
      "data":{"object":{"mode":"payment","client_reference_id":eval_id,
                        "metadata":{"user_id":u.id,"kind":"evaluation"}}}})
db.refresh(ev)
ok("webhook marks paid", ev.paid is True)
ok("  paid_at set", ev.paid_at is not None)

print("── forged webhook does NOT mark paid ──")
ev2 = types.SimpleNamespace()
r2 = B.checkout_evaluation(u, db)
ev2_id = r2["evaluation_id"]
bad_body = json.dumps({"type":"checkout.session.completed",
    "data":{"object":{"mode":"payment","client_reference_id":ev2_id,
                      "metadata":{"user_id":u.id,"kind":"evaluation"}}}}).encode()
class BadReq:
    headers = {"stripe-signature": "bad"}
    async def body(self): return bad_body
orig = B.stripe.Webhook.construct_event
B.stripe.Webhook.construct_event = staticmethod(lambda *a,**k: (_ for _ in ()).throw(ValueError("bad sig")))
try:
    asyncio.run(B.webhook(BadReq(), db))
    ok("forged webhook rejected", False)
except Exception as e:
    ok("forged webhook rejected", "400" in str(e) or "signature" in str(e).lower())
B.stripe.Webhook.construct_event = orig
ev2row = db.query(Evaluation).get(ev2_id)
ok("  still unpaid", ev2row.paid is False)

print("── generating the report (mocked model) ──")
import api.routers.ai as AI
MOCK_REPORT = {
    "readiness_score": 62,
    "headline": "Solid QA foundation, targeting a step up you haven't quite grown into yet",
    "experience_review": {"strengths":["Hands-on automation"],"gaps":["No leadership scope"],
                          "seniority_match":"Targeting Senior with 4 years — a stretch, not impossible"},
    "visa_assessment": {"status":"H1B","risk":"medium","note":"Standard H1B — fine at most employers, some will skip sponsorship entirely"},
    "goal_alignment": {"realistic": False, "note":"1-3 months for a Senior jump on this experience is tight",
                       "timeline_feedback":"3-6 months is more realistic"},
    "next_steps": ["Lead one project end-to-end before applying to Senior roles",
                   "Target Mid-Senior titles alongside Senior to widen the funnel",
                   "Get one strong reference who can speak to ownership"],
    "red_flags": []
}
def _mk_msg(**k):
    return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=json.dumps(MOCK_REPORT))])
AI.client = types.SimpleNamespace(messages=types.SimpleNamespace(create=_mk_msg))
rep = EV.run_evaluation(eval_id, u, db)
ok("report generated", rep.get("readiness_score") == 62)
ok("  covers experience", "experience_review" in rep)
ok("  covers visa", rep["visa_assessment"]["status"]=="H1B")
ok("  covers goals", "goal_alignment" in rep)
ok("  gives concrete next steps", len(rep["next_steps"]) >= 3)
ok("  honest, not just validating", rep["goal_alignment"]["realistic"] is False)

print("── cached on repeat view (no second AI call) ──")
calls_before = None
AI.client.messages.create = lambda **k: (_ for _ in ()).throw(AssertionError("should not call AI again"))
rep2 = EV.run_evaluation(eval_id, u, db)
ok("second call served from cache", rep2["readiness_score"] == 62)

print("── GET reflects paid state ──")
g = EV.get_evaluation(eval_id, u, db)
ok("GET shows paid + report", g["paid"] is True and g["report"]["readiness_score"]==62)

print("── another user cannot read this evaluation ──")
u2 = User(email="other@test.local", name="Other", plan="free", referral_code="other1")
db.add(u2); db.commit(); db.refresh(u2)
try:
    EV.get_evaluation(eval_id, u2, db)
    ok("cross-user read blocked", False)
except Exception as e:
    ok("cross-user read blocked", "404" in str(e))

print("\n" + "=" * 50)
print(f"PASS {P}    FAIL {F}")
if F: print("\nFAILURES"); [print("  ✗ " + f) for f in fails]
else: print("✓ ALL GREEN")
db.close()
os.path.exists("eval_test.db") and os.remove("eval_test.db")
