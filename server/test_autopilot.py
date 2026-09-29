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
ok("a slot is still served when the cron fires an hour late", AP.is_due(cfg, tue_9am_ct + dt.timedelta(hours=1)) == "2026-09-29T09")
ok("not due once the grace window has passed", AP.is_due(cfg, tue_9am_ct + dt.timedelta(hours=3)) is None)
ok("not due before the first slot", AP.is_due(cfg, tue_9am_ct - dt.timedelta(hours=1)) is None)
ok("the later slot is served on its own hour", AP.is_due(cfg, tue_9am_ct + dt.timedelta(hours=4)) == "2026-09-29T13")
ok("not due on weekends", AP.is_due(cfg, sat_9am_ct) is None)
cfg.last_run_key = "2026-09-29T09"
ok("a served slot is not run twice", AP.is_due(cfg, tue_9am_ct) is None)
cfg.tz = "Asia/Kolkata"
ok("slots are read in the user's own zone", AP.is_due(cfg, tue_9am_ct) is None)
cfg.tz, cfg.last_run_key = "America/Chicago", None
cst_tue_9 = dt.datetime(2026, 11, 3, 15, 0, tzinfo=dt.timezone.utc)      # Tue 9:00 CST (after DST ended)
ok("standard time is read correctly after the DST change", AP.is_due(cfg, cst_tue_9) == "2026-11-03T09")
ok("...and 21:00 UTC (4pm CDT) is not a slot", AP.is_due(cfg, dt.datetime(2026, 9, 29, 21, 0, tzinfo=dt.timezone.utc)) is None)
cfg.last_run_key = "2026-09-29T13"
ok("a served later slot also covers the earlier one", AP.is_due(cfg, tue_9am_ct + dt.timedelta(hours=1)) is None)
cfg.last_run_key = None
cfg.paused_until = dt.date(2026, 9, 30)
ok("paused: no run before the resume date", AP.is_due(cfg, tue_9am_ct) is None)
ok("paused: runs again on the resume date", AP.is_due(cfg, tue_9am_ct + dt.timedelta(days=1)) == "2026-09-30T09")
nx = AP.next_run_at(cfg, tue_9am_ct)
ok("next run honours the pause", nx == dt.datetime(2026, 9, 30, 14, 0, tzinfo=dt.timezone.utc), nx)
cfg.paused_until = None
fri_after = dt.datetime(2026, 10, 2, 23, 30, tzinfo=dt.timezone.utc)     # Fri 6:30pm CDT
ok("next run skips the weekend", AP.next_run_at(cfg, fri_after) == dt.datetime(2026, 10, 5, 14, 0, tzinfo=dt.timezone.utc), AP.next_run_at(cfg, fri_after))

# ── matching ──
_, skills = AP._profile_block(db, u)
prof = AP._matcher(db, u, cfg, skills)
cands, counts = AP._candidates(db, u, cfg, prof)
names = [j.fingerprint for _, _, j in cands]
ok("matches by real fit score", "j1" in names and "j4" in names, names)
ok("skips visa-excluded roles", "j3" not in names and counts["visa_blocked"] == 1, (names, dict(counts)))
ok("skips roles below the minimum fit", "j2" not in names, dict(counts))
ok("every candidate clears the floor", all(f >= 60 for f, _, _ in cands), [f for f, _, _ in cands])
ok("candidates are ranked best first", [f for f, _, _ in cands] == sorted((f for f, _, _ in cands), reverse=True))
cfg.min_fit = 100
c100, k100 = AP._candidates(db, u, cfg, prof)
ok("a higher minimum fit filters more", not c100 and k100["below_min_fit"] >= 2, dict(k100))
cfg.min_fit = 60
job("jdead", "Senior SDET", ["Cypress", "Java"], link_status="dead")
job("jnourl", "Senior SDET II", ["Cypress", "Java"]); db.commit(); db.query(Job).filter(Job.fingerprint == "jnourl").update({"apply_url": ""})
old = job("jold", "Senior SDET III", ["Cypress", "Java"]); old.posted_at = now - dt.timedelta(days=60)
db.commit()
c2, k2 = AP._candidates(db, u, cfg, prof)
n2 = [j.fingerprint for _, _, j in c2]
ok("dead links are never queued", "jdead" not in n2 and k2["dead_link"] == 1, dict(k2))
ok("jobs with no apply link are never queued", "jnourl" not in n2 and k2["no_apply_link"] == 1, dict(k2))
ok("stale postings are skipped", "jold" not in n2 and k2["stale_posting"] == 1, dict(k2))
db.query(Job).filter(Job.fingerprint.in_(["jdead", "jnourl", "jold"])).delete(synchronize_session=False); db.commit()
ok("no skills -> no scorer, no candidates", AP._matcher(db, free, AutopilotConfig(user_id=free.id, skills=[], titles=[], work_style="")) is None and AP._candidates(db, free, cfg, None)[0] == [])

# ── run (AI mocked) ──
calls = {"n": 0}
LETTER = "Dear team,\n\nI build and maintain Cypress suites and I would like to bring that to your platform.\n\nThanks."
def fake_call(prompt, max_tokens=1400, label="", fast=False):
    calls["n"] += 1
    ok("autopilot uses the fast model", fast is True)
    return {"subject": "S", "summary": "sum", "highlights": ["a", "b"], "cover_letter": LETTER}
AI._call = fake_call
run = AP.prepare_for(db, u, cfg)
ok("prepares matches", run.prepared == 2 and run.found == 2, (run.prepared, run.found))
ok("run row is finalised, not left 'Running'", run.note is None and run.details.get("min_fit") == 60, (run.note, run.details))
q = AP._queue(db, u)
ok("queued as ready + autopilot", len(q) == 2 and all(a.origin == "autopilot" for a in q))
ok("stores the tailored content", all(a.cover_letter == LETTER for a in q))
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

# ── queue cards: why it matched ──
st = AP._state(db, u)
c0 = st["queue"][0]
ok("queue items carry the real fit score", isinstance(c0["fit"], int) and 60 <= c0["fit"] <= 100, c0)
ok("queue items say which skills matched", "Cypress" in c0["matched_skills"], c0)
ok("state exposes minFit, nextRunAt, email honesty", st["minFit"] == 60 and st["emailConfigured"] is False and "nextRunAt" in st and st["needsSkills"] is False, {k: st[k] for k in ("minFit", "emailConfigured")})

# ── preview: real matcher, no AI, no credits ──
job("jprev", "Lead SDET", ["Cypress"]); db.commit()
before_calls, before_cr = calls["n"], credits.remaining(db, u)
pv = AP.preview_next(u, db)
ok("preview lists the next role with a fit", any(r["fingerprint"] == "jprev" and r["fit"] >= 60 for r in pv["roles"]), pv["roles"])
ok("preview spends nothing and calls no AI", calls["n"] == before_calls and credits.remaining(db, u) == before_cr)
db.query(Job).filter(Job.fingerprint == "jprev").delete(); db.commit()

# ── validation of AI output ──
def bad_figures(prompt, max_tokens=1400, label="", fast=False):
    return {"subject": "S", "summary": "s", "highlights": ["Cut test time by 87%"], "cover_letter": LETTER + " I cut costs by 87% last year."}
def placeholder(prompt, max_tokens=1400, label="", fast=False):
    return {"subject": "S", "summary": "s", "highlights": ["a"], "cover_letter": LETTER + " Sincerely, [Your Name]"}
def malformed(prompt, max_tokens=1400, label="", fast=False):
    return {"subject": "S", "highlights": "not a list", "cover_letter": LETTER}
job("jv1", "Sr SDET Cypress", ["Cypress"]); db.commit()
cr0 = credits.remaining(db, u)
for fn, label in ((bad_figures, "invented figures"), (placeholder, "template placeholders"), (malformed, "malformed structure")):
    AI._call = fn
    db.query(AICache).delete(); db.commit()
    rv = AP.prepare_for(db, u, cfg)
    ok(f"rejects AI drafts with {label}", rv.prepared == 0 and rv.details.get("ai_invalid", 0) >= 1, (rv.prepared, rv.details))
ok("rejected drafts cost no credit and queue nothing", credits.remaining(db, u) == cr0 and not any(a.fingerprint == "jv1" for a in AP._queue(db, u)))
ok("a rejected run says why", "failed our checks" in (rv.note or "") or "checks" in (rv.note or ""), rv.note)
db.query(Job).filter(Job.fingerprint == "jv1").delete(); db.commit()
AI._call = fake_call

# ── re-listing of something already handled ──
job("jrelist", "Senior SDET", ["Cypress", "Java"]); db.commit()
db.query(Job).filter(Job.fingerprint == "jrelist").update({"company": "Co-j1"}); db.commit()
c3, k3 = AP._candidates(db, u, cfg, prof)
ok("same company + title under a new fingerprint is not re-queued", all(j.fingerprint != "jrelist" for _, _, j in c3) and k3["already_handled"] >= 1, dict(k3))
db.query(Job).filter(Job.fingerprint == "jrelist").delete(); db.commit()

# ── queue expiry when a posting closes ──
j4row = db.get(Job, "j4"); j4row.active = False; db.commit()
ids_before = {a.fingerprint for a in AP._queue(db, u)}
ok("closed posting is dropped from the queue", "j4" in ids_before and AP._drop_closed(db, u) == 1 and all(a.fingerprint != "j4" for a in AP._queue(db, u)))
j4row.active = True; db.commit()
jc = db.get(Job, "j1"); jc.link_status = "dead"; db.commit()
try:
    AP.approve(next(a for a in AP._queue(db, u) if a.fingerprint == "j1").id, u, db)
    ok("approving a dead posting is refused", False)
except HTTPException as e:
    ok("approving a dead posting is refused", e.status_code == 409, e.detail)
jc.link_status = None
db.query(Application).filter(Application.user_id == u.id, Application.origin == "autopilot").update({"status": "ready"}); db.commit()
ok("closed items were marked skipped, not deleted", True)

# ── no skills: say so, spend nothing ──
nos = User(email="noskills@aptest.example.com", name="No Skills", plan="pro", account_type="seeker", referral_code="aptestnos")
db.add(nos); db.commit()
ncfg = AutopilotConfig(user_id=nos.id, on=True, slots=[9], titles=["sdet"], resume_confirmed=True); db.add(ncfg); db.commit()
n_before = calls["n"]
rn = AP.prepare_for(db, nos, ncfg)
ok("no skills: nothing queued, no AI, honest note", rn.prepared == 0 and calls["n"] == n_before and "skills" in rn.note.lower() and rn.details.get("needs_skills"), (rn.note, rn.details))
ok("state tells the UI to ask for skills", AP._state(db, nos)["needsSkills"] is True)

# ── daily cap / queue-room messaging ──
u_cap = User(email="cap@aptest.example.com", name="Cap", plan="pro", account_type="seeker", referral_code="aptestcap")
db.add(u_cap); db.commit()
db.add(UserSkill(user_id=u_cap.id, skill="Cypress"))
ccfg = AutopilotConfig(user_id=u_cap.id, on=True, slots=[9], titles=["sdet"], resume_confirmed=True); db.add(ccfg)
db.add(AutopilotRun(user_id=u_cap.id, found=60, prepared=60, skipped=0)); db.commit()
rc = AP.prepare_for(db, u_cap, ccfg)
ok("at the daily limit the note says so (not 'AI unavailable')", rc.prepared == 0 and "Daily limit" in (rc.note or ""), rc.note)

# ── interrupted runs are labelled ──
db.add(AutopilotRun(user_id=u.id, note=AP.RUNNING_NOTE, ran_at=now - dt.timedelta(hours=2))); db.commit()
AP._settle_runs(db, u)
ok("a run cut off mid-way is marked interrupted", db.query(AutopilotRun).filter(
    AutopilotRun.user_id == u.id, AutopilotRun.note.like("Interrupted%")).count() == 1)
ok("per-user run lock refuses a second concurrent run", AP._acquire("x1") and not AP._acquire("x1"))
AP._release("x1")

# ── digest email: only when configured, only reported when sent ──
sent = []
_real_send = AP.mailer.send
AP.mailer.send = lambda to, subj, body: sent.append((to, subj, body)) or True
cfg.slots = [9, 13]; cfg.last_digest_on = None; db.commit()
settings.RESEND_API_KEY = ""
ok("no digest without a mail provider", AP._send_digest(db, u, cfg, "2026-09-29T13") is None and not sent)
settings.RESEND_API_KEY = "re_test"
ok("no digest after a non-final slot", AP._send_digest(db, u, cfg, "2026-09-29T09") is None and not sent)
r_dig = AP._send_digest(db, u, cfg, "2026-09-29T13")
ok("digest sent after the last slot when mail works", r_dig == "sent" and len(sent) == 1 and cfg.last_digest_on == "2026-09-29", (r_dig, sent))
ok("digest says nothing was sent to employers", "Nothing has been sent" in sent[0][2] and "waiting for your review" in sent[0][1])
ok("only one digest a day", AP._send_digest(db, u, cfg, "2026-09-29T13") is None and len(sent) == 1)
cfg.last_digest_on = None
AP.mailer.send = lambda *a: False
ok("a failed send is reported as failed and not marked sent", AP._send_digest(db, u, cfg, "2026-09-29T13") == "failed" and cfg.last_digest_on is None)
cfg.email_digest = False
ok("digest respects the user's opt-out", AP._send_digest(db, u, cfg, "2026-09-29T13") is None)
cfg.email_digest = True
AP.mailer.send = _real_send
settings.RESEND_API_KEY = ""
cfg.slots = [9, 13]; db.commit()

# ── run_due: double tick + failure isolation ──
u2 = User(email="pro2@aptest.example.com", name="Pro Two", plan="pro", account_type="seeker", referral_code="aptestpro2")
db.add(u2); db.commit()
db.add(Position(user_id=u2.id, company="Acme", role="SDET", started_on=dt.date(2020, 1, 1), bullets=["Built Cypress suites"]))
db.add(UserSkill(user_id=u2.id, skill="Cypress"))
cfg2 = AutopilotConfig(user_id=u2.id, on=True, slots=[9], tz="America/Chicago", titles=["sdet"], resume_confirmed=True)
db.add(cfg2)
cfg.last_run_key = None; cfg.last_run_at = None
job("jt1", "Senior SDET Cypress", ["Cypress"]); db.commit()
_real_prepare = AP.prepare_for
def flaky(dbx, user, c, **kw):
    if user.email.startswith("pro2@"): raise RuntimeError("boom")
    return _real_prepare(dbx, user, c, **kw)
AP.prepare_for = flaky
db.query(AutopilotConfig).filter(AutopilotConfig.user_id.notin_([u.id, u2.id])).update({"on": False}, synchronize_session=False); db.commit()
res = AP.run_due(tue_9am_ct)
ok("one user's crash doesn't stop the others", res == {"ran": 1, "failed": 1}, res)
res2 = AP.run_due(tue_9am_ct)
ok("a second tick in the same slot does nothing", res2 == {"ran": 0, "failed": 0}, res2)
AP.prepare_for = _real_prepare
db.refresh(cfg2)
ok("failed user's slot was claimed (no retry storm)", db.get(AutopilotConfig, u2.id).last_run_key == "2026-09-29T09")
cfg = db.get(AutopilotConfig, u.id)
db.query(Application).filter(Application.user_id == u2.id).delete(); db.commit()

# ── settings: new fields validated ──
for bad in (AP.ConfigIn(minFit=101), AP.ConfigIn(minFit=-1), AP.ConfigIn(pausedUntil="soon"), AP.ConfigIn(pausedUntil="2020-01-01"),
            AP.ConfigIn(pausedUntil=(dt.date.today() + dt.timedelta(days=400)).isoformat())):
    try:
        AP.save(bad, u, db); ok(f"rejects {bad.model_dump(exclude_none=True)}", False)
    except HTTPException as e:
        ok(f"rejects {bad.model_dump(exclude_none=True)}", e.status_code == 400, e.detail)
st2 = AP.save(AP.ConfigIn(minFit=75, pausedUntil=(dt.date.today() + dt.timedelta(days=3)).isoformat(), emailDigest=False), u, db)
ok("minFit / pausedUntil / emailDigest persist", st2["minFit"] == 75 and st2["pausedUntil"] and st2["emailDigest"] is False, st2)
st3 = AP.save(AP.ConfigIn(pausedUntil="", minFit=60, emailDigest=True), u, db)
ok("pause can be cleared", st3["pausedUntil"] is None and st3["minFit"] == 60)

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
