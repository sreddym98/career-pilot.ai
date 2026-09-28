# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Ingest pipeline tests. No network: requests.get is replaced by a fake.

    cd server && DATABASE_URL=sqlite:///./ci_ingest.db ENV=dev python3 test_ingest.py
"""
import datetime as dt
import os
import subprocess
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./ci_ingest.db")
os.environ.setdefault("ENV", "dev")
for k in ("RAPIDAPI_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY", "USAJOBS_KEY", "USAJOBS_EMAIL"):
    os.environ.pop(k, None)
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import requests
from ingest import sources, run
from ingest.skills import extract_skills
from api.db import init_db, SessionLocal, engine
from api.models import Job, User, Application

P = F = 0
fails = []


def ok(name, cond, detail=""):
    global P, F
    if cond:
        P += 1
    else:
        F += 1
        fails.append(f"{name} -> {detail}")


# ── fake HTTP ────────────────────────────────────────────────
class Resp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            e = requests.HTTPError(f"HTTP {self.status_code}")
            e.response = self
            raise e

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


ROUTES = {}      # url substring -> Resp | Exception | callable | list (sequence)
CALLS = []
SLEEPS = []


def fake_get(url, **kw):
    CALLS.append(url)
    assert kw.get("timeout"), f"request to {url} has no timeout"
    assert "User-Agent" in (kw.get("headers") or {}), "no User-Agent"
    for key, h in ROUTES.items():
        if key in url:
            if isinstance(h, list):
                h = h.pop(0) if len(h) > 1 else h[0]
            if callable(h):
                h = h()
            if isinstance(h, Exception):
                raise h
            return h
    return Resp(404, {})


requests.get = fake_get
sources._sleep = lambda s: SLEEPS.append(s)
sources.HOST_INTERVAL.clear()


def gh(*jobs):
    return Resp(200, {"jobs": [{"id": i, "title": t, "content": c,
                                "location": {"name": "Remote"},
                                "absolute_url": f"https://x/{i}"} for i, t, c in jobs]})


_OPEN = None


def reset_db():
    # Drop the tables of whatever DATABASE_URL points at, rather than deleting a
    # hard-coded file that only matches the URL in this file's own docstring.
    from api.models import Base
    global _OPEN
    if _OPEN is not None:
        _OPEN.close()          # an idle-in-transaction session blocks DROP TABLE on Postgres
    Base.metadata.drop_all(engine)
    engine.dispose()
    init_db()
    ROUTES.clear(); CALLS.clear(); SLEEPS.clear()
    sources.set_deadline(None)
    _OPEN = SessionLocal()
    return _OPEN


def now():
    return dt.datetime.now(dt.timezone.utc)


BOARD = [("greenhouse", "acme", "Acme")]
JOBS2 = gh((1, "Senior SDET", "Selenium and Java with Jenkins CI/CD. Visa: USC, H1B"),
           (2, "QA Automation Engineer", "Playwright, TypeScript, API testing with Postman"),
           (3, "Account Executive", "sell things"))

# ── 1. idempotent re-ingest ──────────────────────────────────
db = reset_db()
ROUTES["boards-api.greenhouse.io/v1/boards/acme"] = JOBS2
t1 = now()
r1 = run.run_ats(db, t1, BOARD)
rows1 = {j.fingerprint: (j.first_seen, j.seen_count) for j in db.query(Job).all()}
ok("first pass inserts 2 QA jobs, filters the sales role", len(rows1) == 2 and r1[0]["new"] == 2 and r1[0]["skipped"] == 1, r1)
r2 = run.run_ats(db, t1 + dt.timedelta(hours=2), BOARD)
db.expire_all()
rows2 = {j.fingerprint: (j.first_seen, j.seen_count) for j in db.query(Job).all()}
ok("re-run creates no duplicates", set(rows1) == set(rows2) and db.query(Job).count() == 2)
ok("re-run reports seen, not new", r2[0]["new"] == 0 and r2[0]["seen"] == 2, r2)
ok("re-run never resets first_seen", all(rows1[k][0] == rows2[k][0] for k in rows1))
ok("seen_count increments once per run", all(rows2[k][1] == 2 for k in rows2), rows2)
ok("fresh jobs stay active", db.query(Job).filter(Job.active.is_(True)).count() == 2)

# same id twice within one batch must not blow up the commit
dupb = [dict(source="jsearch", source_id="J1", company="Dupco", title="SDET", location="Remote",
             description="Selenium", url="u")] * 3
st = run.ingest_batch(db, dupb, now())
ok("duplicate ids inside one batch insert once", st["new"] == 1 and st["dup"] == 2 and st["bad"] == 0, st)
ok("dup row exists once", db.query(Job).filter(Job.company == "Dupco").count() == 1)

# ── 2. failed / empty fetch never deactivates ────────────────
tt = now() + dt.timedelta(hours=4)
for label, resp in [("HTTP 500", Resp(500, {})), ("HTTP 404", Resp(404, {})),
                    ("network error", requests.ConnectionError("boom")),
                    ("timeout", requests.Timeout("slow")),
                    ("malformed JSON", Resp(200, ValueError("bad json"))),
                    ("empty 200 listing", Resp(200, {"jobs": []}))]:
    ROUTES["boards-api.greenhouse.io/v1/boards/acme"] = resp
    res = run.run_ats(db, tt, BOARD)[0]
    n_active = db.query(Job).filter(Job.source == "greenhouse", Job.active.is_(True)).count()
    ok(f"{label}: existing jobs stay active", n_active == 2 and res["swept"] == 0, (res["err"], n_active))
    if label != "empty 200 listing":
        ok(f"{label}: counted as a failed source", res["ok"] is False and res["err"], res)
ok("empty listing is 'ok' but sweep is skipped", res["ok"] and res["note"] == "empty fetch", res)

# a listing that only has non-QA jobs (all QA roles "vanished" from a 5+ board) is suspicious
ROUTES["boards-api.greenhouse.io/v1/boards/big"] = gh(*[(500 + i, f"SDET {i}", "x") for i in range(10)])
run.run_ats(db, now(), [("greenhouse", "big", "Big")])
ROUTES["boards-api.greenhouse.io/v1/boards/big"] = gh((99, "Cook", "x"))
res = run.run_ats(db, now() + dt.timedelta(hours=1), [("greenhouse", "big", "Big")])[0]
ok("mass-drop on a big board is not swept", res["swept"] == 0 and "suspicious" in res["note"]
   and db.query(Job).filter(Job.company == "Big", Job.active.is_(True)).count() == 10, res)

# a clean listing DOES deactivate what vanished, and reactivating marks relisted
ROUTES["boards-api.greenhouse.io/v1/boards/acme"] = gh((1, "Senior SDET", "Selenium"))
t3 = now() + dt.timedelta(hours=6)
res = run.run_ats(db, t3, BOARD)[0]
active = {j.source_id: j.active for j in db.query(Job).filter(Job.company == "Acme")}
ok("clean full fetch deactivates the vanished job only", active == {"1": True, "2": False} and res["swept"] == 1, (active, res))
first2 = db.query(Job).filter(Job.company == "Acme", Job.source_id == "2").one().first_seen
ROUTES["boards-api.greenhouse.io/v1/boards/acme"] = JOBS2
res = run.run_ats(db, t3 + dt.timedelta(hours=2), BOARD)[0]
db.expire_all()
j2 = db.query(Job).filter(Job.company == "Acme", Job.source_id == "2").one()
ok("reappearing job is reactivated + relisted, first_seen kept", j2.active and j2.relisted and j2.first_seen == first2, (j2.active, j2.relisted))

# aggregators: a failing feed never expires anything, a healthy one ages out only old rows
old = now() - dt.timedelta(days=40)
db.add(Job(fingerprint="agg-old", source="remoteok", source_id="o1", company="OldCo", title="QA Engineer",
           first_seen=old, last_seen=old, active=True, required_skills=[]))
db.commit()
ROUTES.clear()
ROUTES["remoteok.com"] = Resp(503, {})
ROUTES["remotive.com"] = Resp(200, {"jobs": []})
ROUTES["arbeitnow.com"] = Resp(200, {"data": []})
res, exp = run.run_aggregators(db, now(), 21)
ok("failing aggregator does not expire its rows", exp == 0 and db.get(Job, "agg-old").active is True, exp)
ok("failing aggregator is reported", any(r["name"] == "remoteok" and not r["ok"] for r in res))
ROUTES["remoteok.com"] = Resp(200, [{"legal": "x"}, {"id": 7, "position": "QA Lead", "company": "NewCo",
                                                    "description": "Cypress", "url": "u", "location": "Remote"}])
res, exp = run.run_aggregators(db, now(), 21)
db.expire_all()
ok("healthy aggregator expires stale rows only", exp == 1 and db.get(Job, "agg-old").active is False, exp)
ok("healthy aggregator ingested its job", db.query(Job).filter(Job.company == "NewCo", Job.active.is_(True)).count() == 1)

# ── 3. 429 retry with backoff ───────────────────────────────
db = reset_db()
ROUTES["boards-api.greenhouse.io/v1/boards/acme"] = [Resp(429, {}, {"Retry-After": "2"}), Resp(503, {}), JOBS2]
res = run.run_ats(db, now(), BOARD)[0]
ok("429 then 5xx are retried and the fetch succeeds", res["ok"] and res["new"] == 2 and len(CALLS) == 3, (res, len(CALLS)))
ok("Retry-After honoured, then exponential backoff", SLEEPS and 2.0 in SLEEPS, SLEEPS)
CALLS.clear()
ROUTES["boards-api.greenhouse.io/v1/boards/acme"] = Resp(429, {})
res = run.run_ats(db, now() + dt.timedelta(hours=1), BOARD)[0]
ok("persistent 429 gives up after bounded attempts", not res["ok"] and len(CALLS) == sources.MAX_ATTEMPTS, (len(CALLS), res["err"]))
CALLS.clear()
ROUTES["boards-api.greenhouse.io/v1/boards/acme"] = Resp(404, {})
run.run_ats(db, now() + dt.timedelta(hours=2), BOARD)
ok("404 is not retried", len(CALLS) == 1, len(CALLS))

# ── 4. one bad board / one bad row does not abort the run ───
db = reset_db()
boards = [("greenhouse", "dead", "Dead"), ("greenhouse", "weird", "Weird"),
          ("lever", "flaky", "Flaky"), ("greenhouse", "acme", "Acme")]
ROUTES["boards/dead"] = Resp(404, {})
ROUTES["boards/weird"] = Resp(200, {"jobs": ["not-a-dict", 5]})
ROUTES["postings/flaky"] = requests.ConnectionError("reset")
ROUTES["boards/acme"] = JOBS2
results = run.run_ats(db, now(), boards)
by = {r["name"]: r for r in results}
ok("good board ingested despite three bad ones", by["greenhouse/acme"]["ok"] and db.query(Job).filter(Job.company == "Acme").count() == 2, by)
ok("bad boards are logged, not fatal", not by["greenhouse/dead"]["ok"] and not by["lever/flaky"]["ok"] and by["lever/flaky"]["err"])
ok("weird payload is an error, not a crash", not by["greenhouse/weird"]["ok"])

# a poisoned row (unbindable value) costs one row, the rest of the source still commits
recs = [dict(source="s", source_id="a", company="P", title="QA Engineer", location="x", description="d", url="u"),
        dict(source="s", source_id="b", company="P", title="SDET", location="x", description="d", url={"bad": 1}),
        dict(source="s", source_id="c", company="P", title="Test Engineer", location="x", description="d", url="u")]
st = run.ingest_batch(db, recs, now())
ok("poisoned row: others commit, bad counted", st["bad"] == 1 and st["new"] == 2
   and db.query(Job).filter(Job.company == "P").count() == 2, st)
st = run.ingest_batch(db, [dict(source="s", source_id="n", company="NulCo", title="QA Engineer",
                                description="Sel\x00enium", url="u")], now())
ok("NUL bytes stripped (Postgres rejects them)", st["new"] == 1 and "\x00" not in (db.query(Job).filter(Job.company == "NulCo").one().description))

# deadline: nothing fetched, nothing deactivated, marked deferred (not failed)
sources.set_deadline(0.0)
res = run.run_ats(db, now() + dt.timedelta(days=1), BOARD)[0]
sources.set_deadline(None)
ok("time budget exhausted -> deferred, no sweep", res["deferred"] and res["swept"] == 0
   and db.query(Job).filter(Job.company == "Acme", Job.active.is_(True)).count() == 2, res)

# ── exit codes through main() ───────────────────────────────
run.load_boards = lambda: [("greenhouse", "acme", "Acme")]
ROUTES.clear()
os.environ["INGEST_REMOTIVE_EVERY_HOURS"] = "1"
ROUTES["remotive.com"] = Resp(500, {}); ROUTES["remoteok.com"] = Resp(500, {})
ROUTES["arbeitnow.com"] = Resp(500, {}); ROUTES["boards/acme"] = Resp(500, {})
ok("every source failed -> exit 1", run.main(["--once"]) == 1)
ok("failed run deactivated nothing", db.query(Job).filter(Job.company == "Acme", Job.active.is_(True)).count() == 2)
ROUTES["boards/acme"] = JOBS2
ok("some sources failed, some ok -> exit 0", run.main(["--once"]) == 0)
ok("--report exits 0", run.main(["--report"]) == 0)
ok("--fast works", run.main(["--fast"]) in (0, 1))

# ── 5. required_skills extraction ───────────────────────────
sk = extract_skills("SDET", "We use Selenium with Java, TestNG, Postman REST API testing, Jenkins CI/CD, SQL and JMeter. Appium a plus.")
ok("extracts the fixed vocabulary from text", {"Selenium", "Java", "TestNG", "Postman", "API Testing", "Jenkins", "CI/CD", "SQL", "JMeter", "Appium"} <= set(sk), sk)
ok("does not invent skills", extract_skills("QA Engineer", "Great team, free lunch, rest assured we value people.") == [])
ok("Java is not JavaScript", "Java" not in extract_skills("", "JavaScript and TypeScript only") and "JavaScript" in extract_skills("", "JavaScript"))
row = db.query(Job).filter(Job.company == "Acme", Job.source_id == "1").one()
ok("ingested row has required_skills populated", {"Selenium", "Java", "Jenkins", "CI/CD"} <= set(row.required_skills), row.required_skills)
ok("visa flags parsed at ingest", row.visa_usc == "y" and row.visa_h1b == "y", (row.visa_usc, row.visa_h1b))
ok("posted_at / work_mode populated", row.work_mode == "remote" and row.first_seen is not None)
# backfill: a legacy row with empty skills gets them on next sighting
row.required_skills = []; db.commit()
run.run_ats(db, now() + dt.timedelta(days=2), BOARD)
db.expire_all()
ok("legacy row backfilled with skills", db.query(Job).filter(Job.company == "Acme", Job.source_id == "1").one().required_skills)

# ── 6. prune never deletes referenced jobs ──────────────────
db = reset_db()
oldt = now() - dt.timedelta(days=100)
for fp in ("old-free", "old-ref"):
    db.add(Job(fingerprint=fp, source="greenhouse", source_id=fp, company="C", title="SDET",
               first_seen=oldt, last_seen=oldt, active=True, required_skills=[]))
db.add(Job(fingerprint="fresh", source="greenhouse", source_id="f", company="C", title="SDET",
           first_seen=now(), last_seen=now(), active=True, required_skills=[]))
u = User(email="p@example.com", name="P"); db.add(u); db.commit(); db.refresh(u)
db.add(Application(user_id=u.id, fingerprint="old-ref", company="C", title="SDET")); db.commit()
p = run.prune(db, 45)
db.expire_all()
ok("prune deletes unreferenced stale job", db.get(Job, "old-free") is None and p["deleted"] == 1, p)
ok("prune keeps referenced job, deactivated", db.get(Job, "old-ref") is not None and db.get(Job, "old-ref").active is False, p)
ok("prune leaves fresh job alone", db.get(Job, "fresh").active is True)
ok("application still intact", db.query(Application).filter(Application.fingerprint == "old-ref").count() == 1)
db.query(Job).filter(Job.fingerprint == "fresh").update({"last_seen": oldt}); db.commit()
p = run.prune(db, 45)
ok("prune refuses when nothing was seen recently (broken ingest)", p["skipped"] and p["deleted"] == 0 and db.get(Job, "old-ref") is not None, p)
ok("--prune flag runs via main()", run.main(["--prune"]) == 0)

# ── 7. seed.py refuses non-dev ──────────────────────────────
env = {**os.environ, "ENV": "prod", "DATABASE_URL": "postgresql://u:p@127.0.0.1:1/x"}
r = subprocess.run([sys.executable, "seed.py"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
ok("seed.py exits non-zero when ENV=prod", r.returncode != 0 and "REFUSING" in (r.stdout + r.stderr), (r.returncode, r.stderr[-200:]))
env = {**os.environ, "ENV": "dev", "DATABASE_URL": "sqlite:///./ci_ingest_seed.db"}
r = subprocess.run([sys.executable, "seed.py"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
ok("seed.py still works when ENV=dev", r.returncode == 0, r.stderr[-300:])
for f in ("ci_ingest_seed.db",):
    if os.path.exists(os.path.join(ROOT, f)):
        os.remove(os.path.join(ROOT, f))

print(f"PASS {P}    FAIL {F}")
for f in fails:
    print("  FAIL:", f)
sys.exit(1 if F else 0)
