# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Autopilot: schedule, matching, queue, approval. The AI call is mocked."""
import datetime as dt
import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./ci_autopilot.db")
os.environ.setdefault("ENV", "dev")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import HTTPException
from api.db import SessionLocal, init_db
from api.models import (Application, AutopilotConfig, AutopilotRun, Job, Position,
                        User, UserSkill, AICache)
from api.routers import autopilot as AP, ai as AI
from api.settings import production_problems, settings
from api import credits

P = F = 0
fails = []


def ok(name, cond, detail=""):
    global P, F
    if cond: P += 1
    else:
        F += 1; fails.append(f"{name} -> {detail}")


init_db()
db = SessionLocal()
for model in (Application, AutopilotRun, AutopilotConfig, UserSkill, Position):
    db.query(model).delete()
db.query(AICache).delete()
db.query(Job).filter(Job.source == "aptest").delete()
db.query(User).filter(User.email.like("%@aptest.example.com")).delete()
db.commit()

print("\nAUTOPILOT\n")

# ── fixtures ──
u = User(email="pro@aptest.example.com", name="Pat Tester", plan="pro", account_type="seeker",
         headline="Senior SDET", work_auth=["h1b"], referral_code="aptestpro")
free = User(email="free@aptest.example.com", name="Fran Free", plan="free", account_type="seeker",
            referral_code="aptestfree")
db.add_all([u, free]); db.commit()
db.add(Position(user_id=u.id, company="Acme", role="SDET", started_on=dt.date(2020, 1, 1),
                bullets=["Built Cypress suites", "Cut regression time in half"]))
db.add(UserSkill(user_id=u.id, skill="Cypress"))
now = dt.datetime.now(dt.timezone.utc)


def job(fp, title, skills, **kw):
    j = Job(fingerprint=fp, source="aptest", company=f"Co-{fp}", title=title, required_skills=skills,
            active=True, first_seen=now, posted_at=now, apply_url=f"https://x.test/{fp}", **kw)
    db.add(j); return j


job("j1", "Senior SDET", ["Cypress", "Java"])
job("j2", "QA Automation Engineer", ["Selenium"])            # no skill overlap, no title hit
job("j3", "SDET II", ["Cypress"], visa_h1b="n")             # excludes H1B -> filtered
job("j4", "Staff SDET", ["Cypress", "Playwright"], work_mode="remote")
db.commit()

# ── schedule ──
cfg = AutopilotConfig(user_id=u.id, on=True, slots=[9, 13], tz="America/Chicago",
                      titles=["sdet"], skills=[], resume_confirmed=True)
db.add(cfg); db.commit()
tue_9am_ct = dt.datetime(2026, 9, 29, 14, 0, tzinfo=dt.timezone.utc)     # Tue 9:00 CDT
sat_9am_ct = dt.datetime(2026, 10, 3, 14, 0, tzinfo=dt.timezone.utc)
ok("due in a slot on a weekday", AP.is_due(cfg, tue_9am_ct) == "2026-09-29T09", AP.is_due(cfg, tue_9am_ct))
ok("not due outside a slot", AP.is_due(cfg, tue_9am_ct + dt.timedelta(hours=1)) is None)
ok("not due on weekends", AP.is_due(cfg, sat_9am_ct) is None)
cfg.last_run_key = "2026-09-29T09"
ok("a served slot is not run twice", AP.is_due(cfg, tue_9am_ct) is None)
cfg.tz = "Asia/Kolkata"
ok("slots are read in the user's own zone", AP.is_due(cfg, tue_9am_ct) is None)
cfg.tz, cfg.last_run_key = "America/Chicago", None

# ── matching ──
_, skills = AP._profile_block(db, u)
names = [j.fingerprint for _, j in AP._candidates(db, u, cfg, skills)]
ok("matches by title", "j1" in names and "j4" in names, names)
ok("skips visa-excluded roles", "j3" not in names, names)
ok("skips roles with no title or skill match", "j2" not in names, names)

# ── run (AI mocked) ──
calls = {"n": 0}
def fake_call(prompt, max_tokens=1400, label="", fast=False):
    calls["n"] += 1
    ok("autopilot uses the fast model", fast is True)
    return {"subject": "S", "summary": "sum", "highlights": ["a", "b"], "cover_letter": "Dear team"}
AI._call = fake_call
run = AP.prepare_for(db, u, cfg)
ok("prepares matches", run.prepared == 2 and run.found == 2, (run.prepared, run.found))
q = AP._queue(db, u)
ok("queued as ready + autopilot", len(q) == 2 and all(a.origin == "autopilot" for a in q))
ok("stores the tailored content", all(a.cover_letter == "Dear team" for a in q))
ok("spends one generation each", credits.allowance(db, u) - credits.remaining(db, u) == 2)

before = calls["n"]
run2 = AP.prepare_for(db, u, cfg)
ok("never re-prepares a role already queued", run2.prepared == 0 and calls["n"] == before, run2.note)

# ── plan gate ──
fcfg = AutopilotConfig(user_id=free.id, on=True, slots=[9], titles=["sdet"])
db.add(fcfg); db.commit()
ok("free plan prepares nothing", AP.prepare_for(db, free, fcfg).prepared == 0)

# ── AI outage is a skip, not a crash ──
def down(*a, **k): raise HTTPException(503, "down")
AI._call = down
u.credits_used = 0; db.commit()
job("j5", "Principal SDET", ["Cypress"]); db.commit()
r3 = AP.prepare_for(db, u, cfg)
ok("AI outage doesn't raise and prepares nothing", r3.prepared == 0 and r3.skipped >= 1, (r3.prepared, r3.skipped))

# ── approval ──
AI._call = fake_call
item = AP._queue(db, u)[0]
res = AP.approve(item.id, u, db)
ok("approve hands back the posting", res["apply_url"] and res["apply_url"].startswith("https://x.test/"), res)
ok("approved item leaves the queue", all(a.id != item.id for a in AP._queue(db, u)))
try:
    AP.approve(item.id, u, db); ok("double approve refused", False)
except HTTPException as e:
    ok("double approve refused", e.status_code == 400)
try:
    AP.approve(item.id, free, db); ok("cannot approve someone else's item", False)
except HTTPException as e:
    ok("cannot approve someone else's item", e.status_code == 404)
n = len(AP._queue(db, u))
ok("approve-all clears the rest", AP.approve_all(u, db)["approved"] == n and not AP._queue(db, u))

# ── settings + gates ──
try:
    AP.save(AP.ConfigIn(on=True), free, db); ok("free plan can't switch on", False)
except HTTPException as e:
    ok("free plan can't switch on", e.status_code == 402, e.status_code)
settings.TWILIO_ACCOUNT_SID = settings.TWILIO_AUTH_TOKEN = settings.TWILIO_VERIFY_SERVICE_SID = "x"
try:
    AP.save(AP.ConfigIn(on=True), u, db); ok("gates enforced server-side", False)
except HTTPException as e:
    ok("gates enforced server-side", e.status_code == 400 and "phone" in e.detail, e.detail)
settings.TWILIO_ACCOUNT_SID = settings.TWILIO_AUTH_TOKEN = settings.TWILIO_VERIFY_SERVICE_SID = ""
ok("phone gate is off when Twilio is not configured", AP._gates(db, u, cfg)["phoneRequired"] is False)
ok("Autopilot can be switched on without Twilio once the resume is confirmed",
   AP.save(AP.ConfigIn(on=True), u, db) is not None and AP._config(db, u).on is True)
AP.save(AP.ConfigIn(on=False), u, db)
settings.CRON_SECRET = "s3cret"
try:
    AP.diag("wrong"); ok("diag rejects a bad secret", False)
except HTTPException as e:
    ok("diag rejects a bad secret", e.status_code == 401)
AI._call = down
d = AP.diag("s3cret")
ok("diag reports AI failure without raising", str(d["ai_live_call"]).startswith("FAILED"), d)
ok("diag never leaks secret values", "sk_" not in str(d) and "s3cret" not in str(d))
for bad in (AP.ConfigIn(slots=[]), AP.ConfigIn(slots=[25]), AP.ConfigIn(tz="Mars/Base"), AP.ConfigIn(workStyle="moon")):
    try:
        AP.save(bad, u, db); ok(f"rejects {bad.model_dump(exclude_none=True)}", False)
    except HTTPException as e:
        ok(f"rejects {bad.model_dump(exclude_none=True)}", e.status_code == 400)

# ── tick auth ──
class BG:
    def add_task(self, *a, **k): self.ran = True
settings.CRON_SECRET = ""
try:
    AP.tick(BG(), False, "x"); ok("tick closed without CRON_SECRET", False)
except HTTPException as e:
    ok("tick closed without CRON_SECRET", e.status_code == 503)
settings.CRON_SECRET = "s3cret"
for hdr in (None, "wrong"):
    try:
        AP.tick(BG(), False, hdr); ok(f"tick rejects {hdr!r}", False)
    except HTTPException as e:
        ok(f"tick rejects {hdr!r}", e.status_code == 401)
bg = BG()
ok("tick accepts the secret and schedules", AP.tick(bg, False, "s3cret") == {"scheduled": True} and bg.ran)

# ── production guard ──
saved = (settings.ENV, settings.FRONTEND_URL, settings.AUTH_SECRET, settings.DATABASE_URL,
         settings.AI_API_KEY, settings.AI_BASE_URL)
settings.ENV, settings.FRONTEND_URL = "dev", "https://careerpilot.ai"
ok("dev + public URL refuses to start", any("ENV=dev" in p for p in production_problems()))
settings.ENV, settings.FRONTEND_URL, settings.AUTH_SECRET = "prod", "https://careerpilot.ai", ""
settings.DATABASE_URL = "postgresql+psycopg://x"
settings.AI_API_KEY = settings.AI_BASE_URL = ""
probs = " ".join(production_problems())
ok("prod without AUTH_SECRET / AI provider is flagged", "AUTH_SECRET" in probs and "AI provider" in probs, probs)
settings.AUTH_SECRET, settings.AI_API_KEY, settings.AI_BASE_URL = "x" * 48, "k", "https://api.ashna.ai/v1/api"
ok("a fully configured prod passes", production_problems() == [], production_problems())
settings.ENV, settings.FRONTEND_URL, settings.AUTH_SECRET, settings.DATABASE_URL, settings.AI_API_KEY, settings.AI_BASE_URL = saved


# ── in-API job import ──
from api import ingest_job
import time as _t
calls = []
import ingest.run as _R
_orig_cycle = _R.cycle
_R.cycle = lambda db, a, ats=True, agg=True: (calls.append((ats, agg, a.max_seconds, a.workers, a.agg_expire_days)) or 0)
db.query(Application).delete(); db.query(AutopilotRun).delete(); db.query(Job).delete(); db.commit()
ok("empty board triggers a background import", ingest_job.ensure_board_not_empty() is True)
for _ in range(50):
    if not ingest_job.running(): break
    _t.sleep(0.1)
ok("import ran the full pass with a time budget", calls == [(True, True, 600, 4, 21)], calls)
db.add(Job(fingerprint="live1", source="aptest", company="C", title="SDET", required_skills=[], active=True,
           first_seen=now, posted_at=now, apply_url="https://x.test/live1")); db.commit()
ok("a board with jobs is left alone", ingest_job.ensure_board_not_empty() is False and len(calls) == 1)
settings.CRON_SECRET = "s3cret"
try:
    AP.ingest_now("full", "wrong"); ok("ingest endpoint rejects a bad secret", False)
except HTTPException as e:
    ok("ingest endpoint rejects a bad secret", e.status_code == 401)
try:
    AP.ingest_now("nope", "s3cret"); ok("ingest endpoint rejects a bad mode", False)
except HTTPException as e:
    ok("ingest endpoint rejects a bad mode", e.status_code == 400)
r = AP.ingest_now("fast", "s3cret")
for _ in range(50):
    if not ingest_job.running(): break
    _t.sleep(0.1)
ok("ingest endpoint starts a fast run", r["started"] is True and calls[-1][:2] == (False, True), (r, calls))
_R.cycle = _orig_cycle
db.close()
print("=" * 48)
print(f"PASS {P}    FAIL {F}")
if F:
    print("\nFAILURES")
    for f in fails: print("  x " + f)
    raise SystemExit(1)
print("ALL GREEN")
