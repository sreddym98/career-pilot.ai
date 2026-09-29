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

# ── live progress: what the page polls while a run is going ──
db.query(Application).filter(Application.user_id.in_([u.id, free.id])).delete(); db.commit()
pg = User(email="prog@aptest.example.com", name="Prog Tester", plan="pro", account_type="seeker", referral_code="aptestprog")
other = User(email="other@aptest.example.com", name="Other", plan="pro", account_type="seeker", referral_code="aptestother")
db.add_all([pg, other]); db.commit()
db.add(Position(user_id=pg.id, company="Acme", role="SDET", started_on=dt.date(2020, 1, 1), bullets=["Built Cypress suites"]))
db.add(UserSkill(user_id=pg.id, skill="Cypress"))
pcfg = AutopilotConfig(user_id=pg.id, on=True, slots=[9], tz="America/Chicago", titles=["progrole"], resume_confirmed=True)
ocfg = AutopilotConfig(user_id=other.id, on=True, slots=[9], titles=[], resume_confirmed=True)
db.add_all([pcfg, ocfg])
for i in range(3):
    job(f"pg{i}", f"ProgRole SDET {i}", ["Cypress"])
db.commit()
none_yet = AP.progress(pg, db)
ok("progress: no run yet -> run is null, still says on/off", none_yet["run"] is None and none_yet["on"] is True and "now" in none_yet)

seen = []
def watch_call(prompt, max_tokens=1400, label="", fast=False):
    s2 = SessionLocal()
    try:
        v = AP.progress(pg, s2)["run"]; seen.append(v)
        o = AP.progress(other, s2)["run"]
        ok("progress: another user never sees this run", o is None, o)
    finally:
        s2.close()
    return fake_call(prompt, max_tokens, label, fast)
AI._call = watch_call
run_p = AP.prepare_for(db, pg, pcfg)
ok("progress: polled once per role while preparing", len(seen) == 3 and all(v and v["state"] == "running" for v in seen), [v and v["state"] for v in seen])
ok("progress: stage names the role being prepared", seen[0]["stage"].startswith("Preparing application 1 of 3: Co-pg") and "ProgRole SDET" in seen[0]["stage"], seen[0]["stage"])
ok("progress: total is known up front", all(v["total"] == 3 for v in seen), [v["total"] for v in seen])
ok("progress: counts advance only as roles land", [v["prepared"] for v in seen] == [0, 1, 2], [v["prepared"] for v in seen])
st0 = [i["state"] for i in seen[0]["items"]]; st2 = [i["state"] for i in seen[2]["items"]]
ok("progress: items go queued -> preparing -> ready", st0 == ["preparing", "queued", "queued"] and st2 == ["ready", "ready", "preparing"], (st0, st2))
ok("progress: items carry company, role and fit", all(i["company"] and i["title"] and isinstance(i["fit"], int) for i in seen[0]["items"]), seen[0]["items"])
ok("progress: running run has no finish time or note", seen[1]["finishedAt"] is None and seen[1]["note"] is None and seen[1]["startedAt"])
fin = AP.progress(pg, db)["run"]
ok("progress: finished run is Done with every role ready", fin["state"] == "done" and fin["stage"] == "Done" and fin["outcome"] == "ready"
   and fin["prepared"] == 3 and [i["state"] for i in fin["items"]] == ["ready"] * 3 and fin["finishedAt"], fin)
ok("progress: the same run is what the run row says", fin["id"] == run_p.id and run_p.note is None)

# every role's AI call fails -> skipped with a reason, outcome says why
def reset_pg():
    db.query(Application).filter(Application.user_id == pg.id).delete(); db.query(AutopilotRun).filter(AutopilotRun.user_id == pg.id).delete(); db.query(AICache).delete(); db.commit()
reset_pg()
AI._call = down
rd = AP.prepare_for(db, pg, pcfg)
fd = AP.progress(pg, db)["run"]
ok("progress: AI outage -> outcome ai_busy, roles skipped with a reason",
   fd["state"] == "done" and fd["outcome"] == "ai_busy" and fd["prepared"] == 0
   and all(i["state"] == "skipped" and i["reason"] for i in fd["items"]) and "busy" in fd["items"][0]["reason"].lower(), fd)
ok("progress: roles the run gave up before trying say so, not 'ready'",
   any("retry" in (i["reason"] or "") or "AI busy" in (i["reason"] or "") for i in fd["items"]))

# honest reasons for an empty run
reset_pg()
pcfg.min_fit = 100; db.commit()
AP.prepare_for(db, pg, pcfg)
fm = AP.progress(pg, db)["run"]
ok("progress: nothing above minimum fit -> below_min_fit with counts", fm["outcome"] == "below_min_fit" and fm["minFit"] == 100
   and fm["filtered"].get("below_min_fit", 0) >= 1 and fm["items"] == [] and fm["total"] is None, fm)
pcfg.min_fit = 60; db.commit()
db.add(AutopilotRun(user_id=pg.id, found=60, prepared=60, skipped=0)); db.commit()
AP.prepare_for(db, pg, pcfg)
ok("progress: daily cap outcome", AP.progress(pg, db)["run"]["outcome"] == "daily_cap")
reset_pg()
db.query(UserSkill).filter(UserSkill.user_id == pg.id).delete(); pcfg.skills = []; db.commit()
AP.prepare_for(db, pg, pcfg)
ok("progress: no skills outcome", AP.progress(pg, db)["run"]["outcome"] == "needs_skills")
db.add(UserSkill(user_id=pg.id, skill="Cypress")); db.commit()

# a crash mid-run is reported as failed, not left running
reset_pg()
def boom(*a, **k): raise RuntimeError("kaboom")
_pp = AP._prepare_one; AP._prepare_one = boom
AP.prepare_for(db, pg, pcfg); AP._prepare_one = _pp
fe = AP.progress(pg, db)["run"]
ok("progress: unexpected error -> failed with outcome error", fe["state"] == "failed" and fe["outcome"] == "error" and fe["note"], fe)

# stale / interrupted runs never spin forever
reset_pg()
fresh_beat = dt.datetime.now(dt.timezone.utc)
live = AutopilotRun(user_id=pg.id, note=AP.RUNNING_NOTE, ran_at=fresh_beat - dt.timedelta(minutes=5),
                    details={"stage": "Preparing application 1 of 3: X — Y", "heartbeat": (fresh_beat - dt.timedelta(seconds=20)).isoformat(),
                             "total": 3, "items": [{"company": "X", "title": "Y", "fit": 80, "state": "preparing", "reason": None}]})
db.add(live); db.commit()
ok("progress: a long run that keeps reporting is still running", AP.progress(pg, db)["run"]["state"] == "running")
d = dict(live.details); d["heartbeat"] = (fresh_beat - dt.timedelta(seconds=AP.STALE_PROGRESS_S + 30)).isoformat(); live.details = d; db.commit()
sv = AP.progress(pg, db)["run"]
ok("progress: no progress for 3+ minutes -> stale (not running), no finish time", sv["state"] == "stale" and sv["finishedAt"] is None, sv)
ok("progress: stale view keeps what was already prepared", sv["items"][0]["state"] == "preparing" and sv["total"] == 3)
AP._settle_runs(db, pg, AP.STALE_PROGRESS_S)
db.refresh(live)
ok("progress: settling marks it interrupted", (live.note or "").startswith("Interrupted") and live.details["outcome"] == "interrupted")
ok("progress: interrupted settle leaves no item preparing", all(i["state"] == "skipped" for i in AP.progress(pg, db)["run"]["items"]), AP.progress(pg, db)["run"]["items"])
ok("progress: interrupted run is 'stopped' with a finish time", AP.progress(pg, db)["run"]["state"] == "stopped" and AP.progress(pg, db)["run"]["finishedAt"])
# a retry (new run) settles a stale row it finds, and shows the new run
reset_pg()
old_run = AutopilotRun(user_id=pg.id, note=AP.RUNNING_NOTE, ran_at=fresh_beat - dt.timedelta(minutes=6), details={})
db.add(old_run); db.commit()
AI._call = fake_call
rr = AP.prepare_for(db, pg, pcfg)
db.refresh(old_run)
ok("progress: retry settles the dead run and reports the new one", (old_run.note or "").startswith("Interrupted")
   and AP.progress(pg, db)["run"]["id"] == rr.id and AP.progress(pg, db)["run"]["state"] == "done")
ok("progress: /api/autopilot state still lists runs with items", AP._state(db, pg)["runs"][0]["details"].get("items") is not None)
# a scheduled (tick) run leaves the same row the page reads
reset_pg()
pcfg.last_run_key = None; db.commit()
db.query(AutopilotConfig).filter(AutopilotConfig.user_id != pg.id).update({"on": False}, synchronize_session=False); db.commit()
AP.run_due(tue_9am_ct)
ok("progress: a tick-driven run is visible the same way", AP.progress(pg, db)["run"]["state"] == "done" and AP.progress(pg, db)["run"]["prepared"] >= 1)
db.query(Application).filter(Application.user_id.in_([pg.id, other.id])).delete(); db.commit()

# ── add one job on demand + the free starter allowance ──
print("\nADD TO AUTOPILOT / FREE ALLOWANCE\n")
import threading, time as _tm
from fastapi.testclient import TestClient
from sqlalchemy import event as _ev, text as _text
from api.main import app as _app
from api import ratelimit as _RL
from api.db import engine as _engine

_cl = TestClient(_app, raise_server_exceptions=False)
settings.RATE_LIMIT_ENABLED = False
_RL.reset(); AP.reset_breaker()
_RUN = str(int(_tm.time() * 1000))
FAKE_CALLS = {"n": 0}
def slow_ok(prompt, max_tokens=1400, label="", fast=False):
    FAKE_CALLS["n"] += 1
    ok("add-job uses the fast model", fast is True)
    _tm.sleep(0.05)
    return {"subject": "S", "summary": "sum", "highlights": ["a", "b"], "cover_letter": LETTER}
AI._call = slow_ok

def mkuser(tag, plan="free", skills=("Cypress",), position=True, auth=("h1b",)):
    r = _cl.post("/api/auth/signup", json={"email": f"{tag}{_RUN}@aptest.example.com", "password": "Correct-horse-9",
                                           "name": tag.title(), "account_type": "seeker"})
    assert r.status_code == 201, r.text
    d = r.json(); uid = d["user"]["id"]
    with SessionLocal() as s:
        us = s.get(User, uid); us.plan = plan; us.work_auth = list(auth); us.headline = "Senior SDET"
        for k in skills: s.add(UserSkill(user_id=uid, skill=k))
        if position:
            s.add(Position(user_id=uid, company="Acme", role="SDET", started_on=dt.date(2020, 1, 1),
                           bullets=["Built Cypress suites", "Cut regression time in half"]))
        s.commit()
    return uid, {"Authorization": "Bearer " + d["access_token"]}

def mkjob(fp, title="Senior SDET", skills=("Cypress",), **kw):
    kw.setdefault("apply_url", f"https://x.test/{fp}")
    j = Job(fingerprint=fp, source="aptest", company=f"Co-{fp}", title=title, required_skills=list(skills),
            active=True, first_seen=now, posted_at=now, **kw)
    db.add(j); db.commit(); return j

def addj(h, fp):
    r = _cl.post("/api/autopilot/add-job", json={"fingerprint": fp}, headers=h)
    try: return r.status_code, r.json()
    except Exception: return r.status_code, {}

def cfg_of(uid):
    with SessionLocal() as s:
        c = s.get(AutopilotConfig, uid)
        return int(c.free_used or 0) if c else 0
def apps_of(uid):
    with SessionLocal() as s:
        return s.query(Application).filter(Application.user_id == uid).all()
def used_credits(uid):
    with SessionLocal() as s: return s.get(User, uid).credits_used or 0

for i in range(1, 12): mkjob(f"nj{i}", title=f"SDET Level {chr(64+i)}")
mkjob("njdead", link_status="dead"); mkjob("njoff"); db.query(Job).filter(Job.fingerprint == "njoff").update({"active": False})
mkjob("njhttp", apply_url="http://insecure.test/x"); mkjob("njnourl"); db.query(Job).filter(Job.fingerprint == "njnourl").update({"apply_url": ""})
mkjob("njvisa", visa_h1b="n"); mkjob("njlow", title="Registered Nurse", skills=("Patient care", "Triage")); db.commit()

FA, HA = mkuser("fa")
s, r = addj(HA, "nj1")
ok("free add: 200 with the queue item", s == 200 and r["item"]["fingerprint"] == "nj1" and r["alreadyQueued"] is False, (s, r))
ok("  item carries the real fit + reasons", isinstance(r["item"]["fit"], int) and r["item"]["matched_skills"] == ["Cypress"] and "visa" in r["item"], r.get("item"))
ok("  allowance: 1 used, 4 left of 5", (r["freeAllowance"], r["freeUsed"], r["freeLeft"]) == (5, 1, 4), r)
q = [a for a in apps_of(FA) if a.fingerprint == "nj1"]
ok("  same queue as scheduled runs: origin autopilot, status ready, tailored content stored",
   len(q) == 1 and q[0].origin == "autopilot" and q[0].status == "ready" and q[0].cover_letter == LETTER
   and q[0].tailored_resume["highlights"] == ["a", "b"] and q[0].form_fields["subject"] == "S")
ok("  a FREE preparation does not spend a generation credit", used_credits(FA) == 0, used_credits(FA))
st = _cl.get("/api/autopilot", headers=HA).json()
ok("GET /api/autopilot: plan + allowance + the item in the queue",
   st["plan"] == "free" and st["freeAllowance"] == 5 and st["freeUsed"] == 1 and st["freeLeft"] == 4
   and [x["fingerprint"] for x in st["queue"]] == ["nj1"] and st["dailyCap"] == 0 and st["scheduledAvailable"] is False, {k: st[k] for k in ("plan", "freeUsed", "freeLeft", "dailyCap")})
ok("  the on-demand bookkeeping row is not shown as a run", st["runs"] == [], st["runs"])
ok("  ...and is not the 'latest run' the progress card shows", _cl.get("/api/autopilot/progress", headers=HA).json()["run"] is None)
before = FAKE_CALLS["n"]
s, r = addj(HA, "nj1")
ok("idempotent: adding the same job again returns the SAME item, spends nothing, no AI call",
   s == 200 and r["alreadyQueued"] is True and r["freeUsed"] == 1 and FAKE_CALLS["n"] == before and len([a for a in apps_of(FA) if a.fingerprint == "nj1"]) == 1, (s, r))
ok("  ...same queue item id", r["item"]["id"] == q[0].id)

for fp in ("nj2", "nj3", "nj4", "nj5"):
    s, r = addj(HA, fp); ok(f"free add {fp}", s == 200, (s, r))
ok("5 preparations used, 0 left", (r["freeUsed"], r["freeLeft"]) == (5, 0) and cfg_of(FA) == 5, r)
before = FAKE_CALLS["n"]
s, r = addj(HA, "nj6")
ok("the 6th is refused with 402 and an upgrade message", s == 402 and "Upgrade" in r["detail"] and "5" in r["detail"], (s, r))
ok("  the AI was not even called, and nothing was queued or spent", FAKE_CALLS["n"] == before and cfg_of(FA) == 5 and not [a for a in apps_of(FA) if a.fingerprint == "nj6"])

# no gaming: the counter is lifetime, not "items currently in the queue"
ids = [a.id for a in sorted(apps_of(FA), key=lambda a: a.fingerprint)]      # nj1..nj5, in a fixed order on every database
for aid in ids[:2]:
    ok("skip works for a free user (queue stays usable)", _cl.delete(f"/api/autopilot/queue/{aid}", headers=HA).status_code == 200)
ok("skipping items does not give preparations back", addj(HA, "nj6")[0] == 402 and cfg_of(FA) == 5)
with SessionLocal() as s_:                                                   # even deleting the rows outright
    s_.query(Application).filter(Application.user_id == FA, Application.id.in_(ids[2:4])).delete(synchronize_session=False); s_.commit()
ok("deleting queue rows does not give preparations back", addj(HA, "nj7")[0] == 402 and cfg_of(FA) == 5)
ok("re-adding a job you skipped also needs a preparation (blocked at 0)", addj(HA, "nj1")[0] == 402 and cfg_of(FA) == 5)
ap_id = [a for a in apps_of(FA) if a.fingerprint == "nj5"][0].id
ar = _cl.post(f"/api/autopilot/queue/{ap_id}/approve", headers=HA)
ok("Approve still just hands back the apply_url (free users too)", ar.status_code == 200 and ar.json()["apply_url"].startswith("https://x.test/"), ar.text)
ok("approving gives nothing back either", addj(HA, "nj8")[0] == 402 and cfg_of(FA) == 5)
ok("scheduled Autopilot is still Pro-only for free users", _cl.put("/api/autopilot", json={"on": True}, headers=HA).status_code == 402
   and "Pro" in _cl.put("/api/autopilot", json={"on": True}, headers=HA).json()["detail"])
ok("  and a free config never prepares on a schedule", AP.prepare_for(db, db.get(User, FA), AP._config(db, db.get(User, FA))).prepared == 0)

# AI failure / rejected draft costs nothing
FD, HD = mkuser("fd")
AI._call = down
s, r = addj(HD, "nj1")
ok("AI down: 503 that says nothing was used", s == 503 and "Nothing was used" in r["detail"], (s, r))
ok("  no counter spent, nothing queued, no credit spent", cfg_of(FD) == 0 and not apps_of(FD) and used_credits(FD) == 0)
s, r = addj(HD, "nj2")
ok("second failure: same, and it opens the breaker", s == 503 and cfg_of(FD) == 0)
n_calls = {"n": 0}
def counting_ok(prompt, max_tokens=1400, label="", fast=False):
    n_calls["n"] += 1; return {"subject": "S", "summary": "sum", "highlights": ["a", "b"], "cover_letter": LETTER}
AI._call = counting_ok
s, r = addj(HD, "nj3")
ok("breaker open: answers 503 at once WITHOUT calling the AI", s == 503 and n_calls["n"] == 0 and cfg_of(FD) == 0, (s, r, n_calls))
AP.reset_breaker()
def bad_ph(prompt, max_tokens=1400, label="", fast=False):
    return {"subject": "S", "summary": "s", "highlights": ["Led a team of [NUMBER] engineers"], "cover_letter": LETTER}
def bad_fig(prompt, max_tokens=1400, label="", fast=False):
    return {"subject": "S", "summary": "Cut costs by 73%", "highlights": ["a"], "cover_letter": LETTER}
for nm, fn in (("placeholder", bad_ph), ("invented figure", bad_fig)):
    AI._call = fn
    s, r = addj(HD, "nj4")
    ok(f"rejected draft ({nm}): 422, costs nothing", s == 422 and "Nothing was used" in r["detail"] and cfg_of(FD) == 0 and not apps_of(FD), (s, r))
AI._call = counting_ok; AP.reset_breaker()
s, r = addj(HD, "nj4")
ok("after failures, a good draft works and costs exactly 1", s == 200 and cfg_of(FD) == 1 and r["freeLeft"] == 4, (s, r))

# job / profile validation: each refusal is plain English and costs nothing
FV, HV = mkuser("fv")
cases = [("nope-not-a-job", 404, "isn't on the board"), ("njdead", 409, "closed"), ("njoff", 409, "closed"),
         ("njhttp", 400, "https"), ("njnourl", 400, "https"), ("njvisa", 400, "H-1B")]
for fp, code, word in cases:
    s, r = addj(HV, fp)
    ok(f"{fp}: {code} '{word}'", s == code and word in r["detail"], (s, r))
ok("  none of those cost anything", cfg_of(FV) == 0 and not apps_of(FV))
s, r = addj(HV, "njlow")
ok("a below-minimum-fit job CAN be added on purpose (the user chose it), flagged as such",
   s == 200 and r["belowMinFit"] is True and r["item"]["fit"] is not None and r["item"]["fit"] < 60, (s, r.get("item"), r.get("belowMinFit")))
NS, HN = mkuser("ns", skills=(), position=False)
s, r = addj(HN, "nj1")
ok("no skills: 400 'Add your skills first', nothing spent", s == 400 and r["detail"].startswith("Add your skills first") and cfg_of(NS) == 0 and not apps_of(NS), (s, r))
ok("signed-out is refused", _cl.post("/api/autopilot/add-job", json={"fingerprint": "nj1"}, headers={"Authorization": "Bearer nonsense"}).status_code == 401)
ok("bad body is a 422", _cl.post("/api/autopilot/add-job", json={}, headers=HV).status_code == 422)
RC, HR = mkuser("rc")
with SessionLocal() as s_: s_.get(User, RC).account_type = "recruiter"; s_.commit()
ok("recruiter accounts can't use it (403)", addj(HR, "nj1")[0] == 403)

# already applied / re-listing
FR, HRL = mkuser("fr")
with SessionLocal() as s_:
    s_.add(Application(user_id=FR, fingerprint="nj9", company="Co-nj9", title="SDET Level I", status="submitted", origin="manual")); s_.commit()
s, r = addj(HRL, "nj9")
ok("already applied: 409 'already have this job', nothing spent", s == 409 and "already" in r["detail"] and cfg_of(FR) == 0, (s, r))
mkjob("nj9b", title="SDET Level I"); db.query(Job).filter(Job.fingerprint == "nj9b").update({"company": "Co-nj9"}); db.commit()
s, r = addj(HRL, "nj9b")
ok("a re-listing of something already applied to is refused too", s == 409 and cfg_of(FR) == 0, (s, r))

# queue size
FQ, HQ = mkuser("fq")
_mq = AP.MAX_QUEUE; AP.MAX_QUEUE = 1
try:
    addj(HQ, "nj1")
    s, r = addj(HQ, "nj2")
    ok("queue full: 409, nothing spent", s == 409 and "queue is full" in r["detail"] and cfg_of(FQ) == 1, (s, r))
finally:
    AP.MAX_QUEUE = _mq

# skipped-by-you can be re-added deliberately (uses one preparation)
s0 = _cl.delete(f"/api/autopilot/queue/{[a for a in apps_of(FQ)][0].id}", headers=HQ)
s, r = addj(HQ, "nj1")
ok("a job you skipped can be added again on purpose, as ONE fresh item, and it costs a preparation",
   s == 200 and cfg_of(FQ) == 2 and len([a for a in apps_of(FQ) if a.fingerprint == "nj1"]) == 1
   and [a for a in apps_of(FQ) if a.fingerprint == "nj1"][0].status == "ready", (s, r))

# concurrency
FC, HC = mkuser("fcn")
res = []
def click(h, fp):
    with SessionLocal() as s_:
        u_ = s_.get(User, FC)
        try: res.append(("ok", AP.add_job(AP.AddJobIn(fingerprint=fp), u_, s_)))
        except HTTPException as e: res.append((e.status_code, e.detail))
FAKE_CALLS["n"] = 0; AI._call = slow_ok
ts = [threading.Thread(target=click, args=(HC, "nj1")) for _ in range(6)]
[t.start() for t in ts]; [t.join() for t in ts]
ok("6 simultaneous clicks on ONE job: all succeed with the same item, one draft, one preparation",
   all(k == "ok" for k, _ in res) and len({v["item"]["id"] for _, v in res}) == 1 and cfg_of(FC) == 1
   and len(apps_of(FC)) == 1 and FAKE_CALLS["n"] == 1, ([k for k, _ in res], cfg_of(FC), FAKE_CALLS["n"]))
with SessionLocal() as s_: s_.get(AutopilotConfig, FC).free_used = 4; s_.commit()
res.clear()
ts = [threading.Thread(target=click, args=(HC, fp)) for fp in ("nj2", "nj3", "nj4", "nj5")]
[t.start() for t in ts]; [t.join() for t in ts]
oks = [k for k, _ in res if k == "ok"]
ok("4 simultaneous clicks on DIFFERENT jobs with 1 left: exactly one wins, the rest get 402", len(oks) == 1 and sorted(k for k, _ in res if k != "ok") == [402, 402, 402], [k for k, _ in res])
ok("  counter is exactly 5, exactly one new item", cfg_of(FC) == 5 and len(apps_of(FC)) == 2, (cfg_of(FC), len(apps_of(FC))))
# the conditional UPDATE itself (what protects a multi-process deployment): bypass the in-process lock
with SessionLocal() as s_: s_.get(AutopilotConfig, FC).free_used = 4; s_.commit(); s_.query(Application).filter(Application.user_id == FC).delete(); s_.commit()
res2 = []
def raw(fp):
    with SessionLocal() as s_:
        u_ = s_.get(User, FC); j_ = s_.get(Job, fp)
        a, why = AP._prepare_one(s_, u_, j_, "Skills: Cypress\n", charge="free", manual=True)
        res2.append(why or "ok")
ts = [threading.Thread(target=raw, args=(fp,)) for fp in ("nj6", "nj7", "nj8")]
[t.start() for t in ts]; [t.join() for t in ts]
ok("without the lock, the conditional UPDATE still lets exactly one take the last preparation",
   sorted(res2) == ["free_exhausted", "free_exhausted", "ok"] and cfg_of(FC) == 5 and len(apps_of(FC)) == 1, (res2, cfg_of(FC), len(apps_of(FC))))

# isolation between users
FX, HX = mkuser("fx")
s, r = addj(HX, "nj1")
ok("another user adding the same job gets their own item and their own counter", s == 200 and r["item"]["id"] != q[0].id and r["freeUsed"] == 1 and cfg_of(FA) == 5)
ok("  and cannot read or act on someone else's item", _cl.get(f"/api/autopilot/queue/{q[0].id}", headers=HX).status_code == 404
   and _cl.post(f"/api/autopilot/queue/{q[0].id}/approve", headers=HX).status_code == 404)
ok("  their queue lists only their own", [x["fingerprint"] for x in _cl.get("/api/autopilot", headers=HX).json()["queue"]] == ["nj1"])

# Pro
PA, HP = mkuser("pa", plan="pro")
AI._call = slow_ok
for i in range(1, 8):
    s, r = addj(HP, f"nj{i}")
ok("Pro: adds are not limited to 5, use credits (1 each), and never touch the free counter",
   s == 200 and used_credits(PA) == 7 and cfg_of(PA) == 0 and r["plan"] == "pro" and r["freeLeft"] is None, (s, used_credits(PA), cfg_of(PA), r))
stp = _cl.get("/api/autopilot", headers=HP).json()
ok("  Pro state: cap 60, scheduled available, no free counter", stp["dailyCap"] == 60 and stp["scheduledAvailable"] is True and stp["freeLeft"] is None, stp["freeLeft"])
with SessionLocal() as s_:
    s_.add(AutopilotRun(user_id=PA, found=60, prepared=60, skipped=0, note="x")); s_.commit()
s, r = addj(HP, "nj8")
ok("Pro: the daily cap applies to on-demand adds too (429)", s == 429 and "Daily limit" in r["detail"], (s, r))
with SessionLocal() as s_: s_.query(AutopilotRun).filter(AutopilotRun.user_id == PA, AutopilotRun.note == "x").delete(); s_.commit()
with SessionLocal() as s_: s_.get(User, PA).credits_used = 400; s_.commit()
s, r = addj(HP, "nj8")
ok("Pro: out of generations -> 402 with a clear message, nothing queued", s == 402 and "generations" in r["detail"] and not [a for a in apps_of(PA) if a.fingerprint == "nj8"], (s, r))
with SessionLocal() as s_: s_.get(User, PA).credits_used = 0; s_.commit()
_mq = AP.MAX_QUEUE; AP.MAX_QUEUE = 7
s, r = addj(HP, "nj8")
ok("Pro: MAX_QUEUE applies", s == 409 and "queue is full" in r["detail"], (s, r))
AP.MAX_QUEUE = _mq
ok("Pro: scheduled Autopilot toggle still works (resume confirmed)", _cl.post("/api/autopilot/confirm-resume", headers=HP).status_code == 200
   and _cl.put("/api/autopilot", json={"on": True}, headers=HP).json()["on"] is True)

# the jobs list tells the UI each job's Autopilot state without extra calls
lst = _cl.get("/api/jobs?limit=100&sort=new", headers=HA).json()["jobs"]
by = {j["fingerprint"]: j for j in lst}
ok("jobs list: every job has an `autopilot` key", all("autopilot" in j for j in lst) and len(lst) >= 10)
lx = {j["fingerprint"]: j["autopilot"] for j in _cl.get("/api/jobs?limit=100&sort=new", headers=HX).json()["jobs"]}
ok("  queued -> 'queued'; approved -> 'approved'; skipped, deleted or never added -> null",
   lx["nj1"] == "queued" and by["nj5"]["autopilot"] == "approved"
   and by["nj1"]["autopilot"] is None and by["nj2"]["autopilot"] is None and by["nj8"]["autopilot"] is None,
   ({k: v["autopilot"] for k, v in by.items() if k.startswith("nj")}, lx.get("nj1")))
_so = _cl.get("/api/jobs?limit=100&sort=new")      # dev mode signs an anonymous caller in, so probe with no header at all only for shape
ok("  a bad/expired token is treated as signed out: null everywhere", all(j["autopilot"] is None for j in _cl.get("/api/jobs?limit=100&sort=new", headers={"Authorization": "Bearer nonsense"}).json()["jobs"]))
ok("  one user's state never shows on another's list", all(j["autopilot"] is None for j in _cl.get("/api/jobs?limit=100&sort=new", headers=HD).json()["jobs"] if j["fingerprint"] not in ("nj1", "nj4")))
ok("  the single-job endpoint carries it too", _cl.get("/api/jobs/nj5", headers=HA).json()["autopilot"] == "approved"
   and _cl.get("/api/jobs/nj1", headers=HX).json()["autopilot"] == "queued")
stmts = []
def _cap_sql(conn, cur, statement, *a): stmts.append(statement)
_ev.listen(_engine, "before_cursor_execute", _cap_sql)
_cl.get("/api/jobs?limit=100&sort=new", headers=HA)
_ev.remove(_engine, "before_cursor_execute", _cap_sql)
apq = [x for x in stmts if "FROM applications" in x]
ok("  computed with ONE applications query for the whole page (no N+1)", len(apq) == 1, len(apq))

# rate limit
settings.RATE_LIMIT_ENABLED = True; _RL.reset()
settings.RATE_AUTOPILOT_ADD = 3
RL_U, HRLU = mkuser("rl", plan="pro")
codes = [addj(HRLU, "nj1")[0] for _ in range(5)]
r_ = _cl.post("/api/autopilot/add-job", json={"fingerprint": "nj1"}, headers=HRLU)
ok("rate limit: per-user cap on add-job -> 429 with Retry-After", codes[:3] == [200, 200, 200] and codes[3:] == [429, 429] and r_.headers.get("retry-after"), (codes, r_.headers))
ok("  another user is not affected", addj(HX, "nj2")[0] == 200)
settings.RATE_AUTOPILOT_ADD = 12; settings.RATE_AUTOPILOT_ADD_PER_IP = 2; _RL.reset()
codes = [addj(HX, "nj1")[0] for _ in range(4)]
ok("  and a per-IP ceiling across accounts", codes.count(429) >= 1, codes)
settings.RATE_AUTOPILOT_ADD_PER_IP = 40; settings.RATE_LIMIT_ENABLED = False; _RL.reset()

# migration: the counter column is added to a live table by add_missing_columns; existing rows read 0.
# Done in a fresh process: SQLite connections that have already cached the table's schema can't be
# trusted to see a DROP/ADD of the same column made under them.
import subprocess as _sp
db.rollback()
_mig = """
import os, sys
sys.path.insert(0, os.getcwd())
from sqlalchemy import text, inspect
from api.db import engine, init_db, SessionLocal
from api.models import AutopilotConfig, User
from api.routers import autopilot as AP
with engine.begin() as c:
    c.execute(text("ALTER TABLE autopilot_configs DROP COLUMN free_used"))
assert "free_used" not in {c["name"] for c in inspect(engine).get_columns("autopilot_configs")}
init_db()
assert "free_used" in {c["name"] for c in inspect(engine).get_columns("autopilot_configs")}, "column not added"
with SessionLocal() as s:
    rows = s.query(AutopilotConfig).all()
    assert rows and all(int(r.free_used or 0) == 0 for r in rows), "existing rows must read 0"
    u = s.get(User, rows[0].user_id)
    assert AP._allowance(u, rows[0])["freeUsed"] == 0
    assert AP._spend_free(s, u) is True, "conditional spend on a migrated row"
    s.refresh(rows[0]); assert rows[0].free_used == 1
    for _ in range(4): assert AP._spend_free(s, u) is True
    assert AP._spend_free(s, u) is False, "6th spend must fail"
    rows[0].free_used = 0; s.commit()
init_db()   # idempotent
print("MIGRATION-OK")
"""
_r = _sp.run([sys.executable, "-c", _mig], capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__)))
ok("migration: free_used is added to a live table, existing rows read 0, conditional spend works, re-run is a no-op",
   "MIGRATION-OK" in _r.stdout, (_r.stdout + _r.stderr)[-600:])
AI._call = fake_call
db.expire_all()

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
