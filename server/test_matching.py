# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Fit-score tests: the score comes from real profile data and is null when
there isn't any.

    cd server && DATABASE_URL=sqlite:///./ci_matching.db ENV=dev python3 test_matching.py
"""
import datetime as dt
import os
import sys
import time
import types

os.environ.setdefault("DATABASE_URL", "sqlite:///./ci_matching.db")
os.environ.setdefault("ENV", "dev")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

P = F = 0
fails = []


def ok(name, cond, detail=""):
    global P, F
    if cond:
        P += 1
    else:
        F += 1
        fails.append(f"{name} -> {detail}")


from fastapi.testclient import TestClient
from api.main import app
from api.db import init_db, SessionLocal, engine
from api.models import Base, User, Job, Position, UserSkill, AutopilotConfig
from api import matching as M
from api import ratelimit as RL

Base.metadata.drop_all(engine)
engine.dispose()
init_db()
client = TestClient(app, raise_server_exceptions=False)
db = SessionLocal()
RL.reset()
RUN = str(int(time.time() * 1000))
TODAY = dt.date.today()


def pos(role, start, end=None, bullets=()):
    return types.SimpleNamespace(role=role, started_on=start, finished_on=end, bullets=list(bullets))


def job(title="QA Engineer", skills=(), **k):
    d = dict(title=title, required_skills=list(skills), exp_min=None, exp_max=None, work_mode=None,
             visa_usc="u", visa_gc="u", visa_h1b="u", visa_opt="u")
    d.update(k)
    return types.SimpleNamespace(**d)


def prof(skills=("Selenium", "Java", "SQL"), positions=None, headline="", auth=(), style=""):
    if positions is None:
        positions = [pos("Senior SDET", TODAY - dt.timedelta(days=365 * 6))]
    return M.Profile(list(skills), positions, headline, list(auth), style)


# ── unit: skills ─────────────────────────────────────────────
p = prof()
r = M.score_job(p, job(skills=["Selenium", "Java", "SQL", "Kafka"]))
ok("matched/missing skills reported", r["fit_reasons"]["matched_skills"] == ["Selenium", "Java", "SQL"]
   and r["fit_reasons"]["missing_skills"] == ["Kafka"], r)
ok("skills-only basis is honest", "skills" in r["fit_reasons"]["basis"], r)
full = M.score_job(p, job(skills=["Selenium", "Java"]))["fit"]
half = M.score_job(p, job(skills=["Selenium", "Kafka"]))["fit"]
none_ = M.score_job(p, job(skills=["Kafka", "Snowflake"]))["fit"]
ok("more overlap -> higher fit (monotonic)", full > half > none_, (full, half, none_))
ok("fit is an int 0..100", all(isinstance(x, int) and 0 <= x <= 100 for x in (full, half, none_)))
ok("no overlap and a different title scores low", M.score_job(p, job("Account Executive", ["Salesforce"]))["fit"] < 20)
ok("alias: JS/Node.js == JavaScript, Postgres == PostgreSQL",
   M.score_job(prof(["JS", "Postgres"]), job(skills=["JavaScript", "PostgreSQL"]))["fit_reasons"]["missing_skills"] == [])
ok("substring must be a whole word: Java != JavaScript, SQL != PostgreSQL",
   M.score_job(prof(["JavaScript", "PostgreSQL"]), job(skills=["Java", "SQL"]))["fit_reasons"]["matched_skills"] == [])
ok("PySpark implies Spark", M.score_job(prof(["PySpark"]), job(skills=["Spark"]))["fit_reasons"]["matched_skills"] == ["Spark"])
ok("skills used in position bullets count",
   "Cypress" in M.score_job(prof(["Java"], [pos("QA", TODAY - dt.timedelta(days=400), None, ["Built Cypress suites"])]),
                            job(skills=["Cypress"]))["fit_reasons"]["matched_skills"])

# ── unit: title ──────────────────────────────────────────────
same = M.score_job(prof(["X"], headline=""), job("Sr. SDET", []))
ok("title-only score works when the job lists no skills", same["fit"] is not None and same["fit_reasons"]["basis"][0] == "title", same)
ok("SDET vs QA Automation Engineer overlap",
   M.score_job(prof(["X"]), job("QA Automation Engineer", []))["fit"] >= 50)
ok("unrelated title, no skills -> low", M.score_job(prof(["X"]), job("Sales Director", []))["fit"] <= 10)
ok("a job with neither skills nor a comparable title gets None, not a made-up number",
   M.score_job(prof(["X"], positions=[]), job("QA Engineer", []))["fit"] is None)

# ── unit: experience ─────────────────────────────────────────
ok("overlapping roles counted once",
   abs(M.years_of_experience([pos("a", dt.date(2020, 1, 1), dt.date(2022, 1, 1)),
                              pos("b", dt.date(2021, 1, 1), dt.date(2023, 1, 1))]) - 3.0) < 0.05)
ok("years within the range: full marks", M._exp_score(6, 5, 8) == 1.0)
ok("under-experienced lowers the score", 0 < M._exp_score(3, 8, None) < 0.7)
ok("over-qualified is mild", M._exp_score(20, 3, 5) >= 0.7)
ok("no range stated -> not scored", M._exp_score(6, None, None) is None)
a = M.score_job(prof(), job(skills=["Selenium"], exp_min=5, exp_max=8))["fit"]
b = M.score_job(prof(), job(skills=["Selenium"], exp_min=15, exp_max=20))["fit"]
ok("experience gap lowers fit", a > b, (a, b))

# ── unit: work mode / visa ───────────────────────────────────
ok("work-mode preference counted only when stated",
   "work_mode" not in M.score_job(prof(), job(skills=["Java"], work_mode="remote"))["fit_reasons"]["basis"]
   and "work_mode" in M.score_job(prof(style="remote"), job(skills=["Java"], work_mode="remote"))["fit_reasons"]["basis"])
ok("remote-only seeker penalises on-site",
   M.score_job(prof(style="remote"), job(skills=["Java"], work_mode="onsite"))["fit"]
   < M.score_job(prof(style="remote"), job(skills=["Java"], work_mode="remote"))["fit"])
v = M.score_job(prof(auth=["h1b"]), job(skills=["Selenium", "Java", "SQL"], visa_h1b="n"))
ok("explicit 'n' for the seeker's status is a hard mismatch", v["fit"] == 0 and v["fit_reasons"]["blocked"] and v["fit_reasons"]["visa"] == "blocked", v)
ok("'u' (not stated) is not a mismatch", M.score_job(prof(auth=["h1b"]), job(skills=["Java"]))["fit"] > 0)
ok("blocked only if EVERY held status is excluded",
   M.score_job(prof(auth=["h1b", "gc"]), job(skills=["Java"], visa_h1b="n", visa_gc="y"))["fit"] > 0)
ok("stated 'y' is surfaced",
   M.score_job(prof(auth=["opt"]), job(skills=["Java"], visa_opt="y"))["fit_reasons"]["visa"] == "stated_yes")
ok("no work_auth on profile -> visa not evaluated",
   M.score_job(prof(), job(skills=["Java"], visa_h1b="n"))["fit_reasons"]["visa"] is None)

# ── unit: null when no data ──────────────────────────────────
ok("score_job(None) is null, no reasons", M.score_job(None, job(skills=["Java"])) == {"fit": None, "fit_reasons": None})
ok("no saved skills -> no profile", M.load_profile(db, None) is None)

# ── HTTP: signed out / no skills / with skills ───────────────
def signup(tag):
    r = client.post("/api/auth/signup", json={"email": f"{tag}{RUN}@match.example.com", "password": "Correct-horse-9",
                                              "name": tag, "account_type": "seeker"})
    assert r.status_code == 201, r.text
    d = r.json()
    return d["user"]["id"], {"Authorization": "Bearer " + d["access_token"]}


def J(fp, title, skills, **k):
    d = dict(fingerprint=fp, source="greenhouse", source_id=fp, company=f"Co-{fp}", title=title, required_skills=skills,
             active=True, apply_url=f"https://boards.greenhouse.io/co/jobs/{fp}",
             first_seen=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=ord(fp[0]) - 96))
    d.update(k)
    return Job(**d)


db.add_all([
    J("aaaa", "Senior SDET", ["Selenium", "Java", "SQL", "Jenkins"]),
    J("bbbb", "QA Automation Engineer", ["Selenium", "Java"]),
    J("cccc", "Account Executive", ["Salesforce"]),
    J("dddd", "SDET", ["Selenium", "Java", "SQL"], visa_h1b="n"),
    J("eeee", "Data QA Engineer", ["Snowflake", "Airflow"]),
    J("ffff", "QA Engineer", [], source="remoteok", link_status="ok", verified_at=dt.datetime.now(dt.timezone.utc)),
])
db.commit()

anon = client.get("/api/jobs", headers={"Authorization": "Bearer not-a-real-token"})
ok("signed out: 200 and fit is null on every job", anon.status_code == 200 and anon.json()["jobs"]
   and all(j["fit"] is None and j["fit_reasons"] is None for j in anon.json()["jobs"]), anon.text[:200])
ok("signed out: fit_available false", anon.json().get("fit_available") is False)
ok("signed out: sort=match still returns rows (newest first)",
   [j["fingerprint"] for j in client.get("/api/jobs?sort=match", headers={"Authorization": "Bearer bad"}).json()["jobs"]][0] == "aaaa")

uid, H = signup("noskills")
r = client.get("/api/jobs", headers=H).json()
ok("signed in with NO skills: fit null everywhere", not r["fit_available"] and all(j["fit"] is None for j in r["jobs"]), r["fit_available"])

uid, H = signup("skilled")
u = db.get(User, uid)
u.headline = "Senior SDET"; u.work_auth = ["h1b"]; db.commit()
db.add_all([UserSkill(user_id=uid, skill=s) for s in ("Selenium", "Java", "SQL")])
db.add(Position(user_id=uid, company="X", role="Senior SDET", started_on=TODAY - dt.timedelta(days=365 * 7)))
db.commit()

r = client.get("/api/jobs?sort=match", headers=H).json()
by = {j["fingerprint"]: j for j in r["jobs"]}
ok("with skills: fit_available and ints", r["fit_available"] and all(isinstance(j["fit"], int) or j["fit"] is None for j in r["jobs"]))
ok("best-matching job outranks weak ones", by["aaaa"]["fit"] > by["eeee"]["fit"] and by["bbbb"]["fit"] > by["cccc"]["fit"],
   {k: v["fit"] for k, v in by.items()})
ok("h1b-excluded job is a hard mismatch (0, blocked)", by["dddd"]["fit"] == 0 and by["dddd"]["fit_reasons"]["blocked"])
ok("reasons carry matched + missing skills",
   by["aaaa"]["fit_reasons"]["matched_skills"] == ["Selenium", "Java", "SQL"] and by["aaaa"]["fit_reasons"]["missing_skills"] == ["Jenkins"])
order = [j["fit"] for j in r["jobs"] if j["fit"] is not None]
ok("sort=match is descending by fit", order == sorted(order, reverse=True), order)
top = r["jobs"][0]
ok("top result is the strongest fit", top["fit"] == max(order))
r2 = client.get("/api/jobs?sort=new", headers=H).json()
ok("sort=new keeps recency order, fit still attached", r2["jobs"][0]["fingerprint"] == "aaaa" and r2["jobs"][0]["fit"] is not None)
r3 = client.get("/api/jobs?min_fit=60", headers=H).json()
ok("min_fit filters on the server fit", r3["jobs"] and all(j["fit"] >= 60 for j in r3["jobs"]) and r3["total"] == len(r3["jobs"]),
   [j["fit"] for j in r3["jobs"]])
p1 = client.get("/api/jobs?sort=match&limit=2&offset=0", headers=H).json()
p2 = client.get("/api/jobs?sort=match&limit=2&offset=2", headers=H).json()
ok("paging follows match order", [j["fit"] for j in p1["jobs"] + p2["jobs"]] == [j["fit"] for j in r["jobs"]][:4]
   and p1["total"] == r["total"])
d = client.get("/api/jobs/aaaa", headers=H).json()
ok("job detail carries fit + reasons", d["fit"] == by["aaaa"]["fit"] and d["fit_reasons"]["missing_skills"] == ["Jenkins"])
ok("job detail signed out: null", client.get("/api/jobs/aaaa", headers={"Authorization": "Bearer bad"}).json()["fit"] is None)

# preference from autopilot config is used, and only when stated
db.add(AutopilotConfig(user_id=uid, work_style="remote", titles=[])); db.commit()
db.query(Job).filter(Job.fingerprint == "aaaa").update({"work_mode": "onsite"}); db.commit()
dd = client.get("/api/jobs/aaaa", headers=H).json()["fit_reasons"]
ok("stated work_style enters the basis and explains itself", "work_mode" in dd["basis"] and "remote" in (dd["work_mode"] or ""), dd)

# ── verified / source shape ──────────────────────────────────
ok("API: verified true only with a successful link check", by["ffff"]["verified"] is True and by["aaaa"]["verified"] is False)
ok("API: source + direct exposed", by["aaaa"]["source"] == "greenhouse" and by["aaaa"]["direct"] is True
   and by["ffff"]["source"] == "remoteok" and by["ffff"]["direct"] is False)
ok("API: blocked/unchecked links are never 'verified'",
   client.get("/api/jobs", headers=H).json()["jobs"] and all(not j["verified"] for j in r["jobs"] if j["link_status"] != "ok"))

# ── migration: old tables gain the new nullable columns ─────
from sqlalchemy import text, inspect
with engine.begin() as c:
    for col in ("verified_at", "link_checked_at", "link_status", "link_http"):
        try:
            c.execute(text(f"ALTER TABLE jobs DROP COLUMN {col}"))
        except Exception:
            pass
init_db()
cols = {c["name"] for c in inspect(engine).get_columns("jobs")}
ok("init_db re-adds link-verification columns to an existing jobs table",
   {"verified_at", "link_checked_at", "link_status", "link_http"} <= cols, cols)
ok("existing rows survive with NULL verification", db.query(Job).count() >= 6
   and client.get("/api/jobs?limit=1").json()["jobs"][0]["verified"] in (True, False))

print(f"PASS {P}    FAIL {F}")
for f in fails:
    print("  FAIL:", f)
sys.exit(1 if F else 0)
