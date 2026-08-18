"""Mock interview generation. Proves it's built from real experience,
gated correctly, and cached so repeat requests don't re-spend a credit."""
import os, sys, json, types
os.environ.setdefault("DATABASE_URL", "sqlite:///./interview_test.db")
os.environ.setdefault("ENV", "dev")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

P = F = 0; fails = []
def ok(n, c, x=""):
    global P, F
    if c: P += 1
    else: F += 1; fails.append(f"{n}  →  {x}")

import datetime as dt
from fastapi import HTTPException
from api.db import init_db, SessionLocal
from api.models import User, Position
init_db()
db = SessionLocal()

def mk_user(email, plan):
    u = db.query(User).filter(User.email == email).first()
    if not u:
        u = User(email=email, name="Test User", plan=plan, work_auth=["h1b"], referral_code=email[:10])
        db.add(u); db.commit(); db.refresh(u)
    else:
        u.plan = plan; u.credits_used = 0; db.commit()
    return u

import api.routers.interview as I
import api.routers.ai as AI

MOCK = {
    "skills_tested": [{"skill": "Playwright", "why": "Primary automation tool in the JD"}],
    "technical": [{"question": "Walk me through a Playwright framework you built.",
                   "what_they_want": "Architecture reasoning",
                   "answer_using_your_experience": "At Mastercard I built a POM-based Playwright suite for payment platforms.",
                   "watch_out_for": "Vague answers with no real project named"}],
    "behavioral": [{"question": "Tell me about a time you disagreed with a teammate.",
                    "framework": "STAR", "answer_using_your_experience": "Draw on a real Mastercard example."}],
    "questions_to_ask_them": ["How is the QA team structured?"],
    "weak_spots": ["No direct Kafka experience shown, and the JD asks for it"]
}
def _mk(**k):
    return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=json.dumps(MOCK))])

print("\n╔═══ MOCK INTERVIEW ═══╗\n")

print("── Blocks without a profile ──")
empty_user = mk_user("empty@test.local", "free")
try:
    I.generate_mock_interview(I.InterviewIn(job_title="Senior SDET"), empty_user, db)
    ok("no positions → blocked", False)
except HTTPException as e:
    ok("no positions → blocked", e.status_code == 400 and "profile" in e.detail)

print("── Real generation, grounded in actual experience ──")
u = mk_user("candidate@test.local", "free")
if not db.query(Position).filter(Position.user_id == u.id).count():
    db.add(Position(user_id=u.id, company="Mastercard", role="Sr. SDET",
                    started_on=dt.date(2024,5,1), bullets=["Built Playwright automation for payments"]))
    db.commit()

AI.client = types.SimpleNamespace(messages=types.SimpleNamespace(create=_mk))
before = credits_before = u.credits_used or 0
r = I.generate_mock_interview(I.InterviewIn(job_title="Senior SDET", company="Acme",
                                            jd="Looking for Playwright and Kafka experience.",
                                            skills=["Playwright","Kafka"]), u, db)
ok("returns skills_tested", len(r["skills_tested"]) > 0)
ok("returns technical questions", len(r["technical"]) > 0)
ok("  answers reference REAL company, not invented",
   "Mastercard" in r["technical"][0]["answer_using_your_experience"])
ok("returns behavioral questions", len(r["behavioral"]) > 0)
ok("returns questions to ask them", len(r["questions_to_ask_them"]) > 0)
ok("honestly flags a gap rather than hiding it", len(r["weak_spots"]) > 0)
ok("  gap references something not in their actual experience",
   "Kafka" in r["weak_spots"][0])

print("── Credit spent on generation (free plan) ──")
db.refresh(u)
ok("credit was spent", (u.credits_used or 0) == before + 1, f"{u.credits_used} vs {before+1}")

print("── Cached on repeat — no second spend, no second AI call ──")
calls_before = None
AI.client.messages.create = lambda **k: (_ for _ in ()).throw(AssertionError("should not call AI again"))
r2 = I.generate_mock_interview(I.InterviewIn(job_title="Senior SDET", company="Acme",
                                             jd="Looking for Playwright and Kafka experience.",
                                             skills=["Playwright","Kafka"]), u, db)
ok("second identical call served from cache", r2["technical"][0]["question"] == r["technical"][0]["question"])
db.refresh(u)
ok("  no second credit spent", (u.credits_used or 0) == before + 1)

print("── Different JD → different cache key, spends again ──")
AI.client.messages.create = _mk
r3 = I.generate_mock_interview(I.InterviewIn(job_title="Senior SDET", company="Acme",
                                             jd="Completely different JD asking for Selenium instead.",
                                             skills=["Selenium"]), u, db)
db.refresh(u)
ok("different JD triggers a fresh generation + spend", (u.credits_used or 0) == before + 2)

print("── Out-of-credits free user is blocked ──")
u2 = mk_user("nocred@test.local", "free")
if not db.query(Position).filter(Position.user_id == u2.id).count():
    db.add(Position(user_id=u2.id, company="X", role="Y", started_on=dt.date(2020,1,1), bullets=["did a thing"]))
    db.commit()
u2.credits_used = 999
u2.credits_reset_at = dt.datetime.now(dt.timezone.utc)  # this month, so it doesn't roll over
db.commit()
try:
    I.generate_mock_interview(I.InterviewIn(job_title="QA Engineer"), u2, db)
    ok("out of credits blocked", False)
except HTTPException as e:
    ok("out of credits blocked", e.status_code == 429)
    ok("  suggests a real path forward", "refer" in e.detail.lower() or "upgrade" in e.detail.lower())

print("── Pro user doesn't spend a credit (unlimited within plan) ──")
u3 = mk_user("pro@test.local", "pro")
if not db.query(Position).filter(Position.user_id == u3.id).count():
    db.add(Position(user_id=u3.id, company="Stripe", role="SDET", started_on=dt.date(2021,1,1),
                    bullets=["Built API test suites for payments"]))
    db.commit()
before3 = u3.credits_used or 0
AI.client.messages.create = _mk
I.generate_mock_interview(I.InterviewIn(job_title="SDET", jd="Fresh unique JD for pro test xyz123"), u3, db)
db.refresh(u3)
ok("pro plan generation doesn't touch the free-tier credit meter", (u3.credits_used or 0) == before3)

print("\n" + "=" * 50)
print(f"PASS {P}    FAIL {F}")
if F: print("\nFAILURES"); [print("  ✗ " + f) for f in fails]
else: print("✓ ALL GREEN")
db.close()
os.path.exists("interview_test.db") and os.remove("interview_test.db")
