# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""The Apply page API, employer questions, tailored resume, and the extension
key. The AI and the employer ATS are mocked; normalisers run on recorded
fixtures shaped like the documented Greenhouse / Lever responses.

    cd server; python test_apply.py
"""
import datetime as dt
import json
import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./ci_apply.db")
os.environ.setdefault("ENV", "dev")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from api.main import app
from api.db import SessionLocal, init_db
from api.models import (AICache, Application, ATSQuestions, AutopilotConfig, AutopilotRun, ExtensionToken,
                        Job, Position, User, UserSkill)
from api import ats, resume as R, tokens
from api.routers import ai as AI, autopilot as AP

HERE = os.path.dirname(os.path.abspath(__file__))
GH = json.load(open(os.path.join(HERE, "fixtures", "greenhouse_job_questions.json")))
LV = json.load(open(os.path.join(HERE, "fixtures", "lever_posting.json")))

P = F = 0
fails = []


def ok(name, cond, detail=""):
    global P, F
    if cond: P += 1
    else:
        F += 1; fails.append(f"{name} -> {detail}")


init_db()
db = SessionLocal()
mine = db.query(User).filter(User.email.like("%@applytest.example.com")).all()
ids = [u.id for u in mine]
if ids:
    db.query(ExtensionToken).filter(ExtensionToken.user_id.in_(ids)).delete(synchronize_session=False)
    db.query(Application).filter(Application.user_id.in_(ids)).delete(synchronize_session=False)
    db.query(AutopilotRun).filter(AutopilotRun.user_id.in_(ids)).delete(synchronize_session=False)
    db.query(AutopilotConfig).filter(AutopilotConfig.user_id.in_(ids)).delete(synchronize_session=False)
    for u in mine: db.delete(u)
db.query(ATSQuestions).filter(ATSQuestions.fingerprint.like("apt-%")).delete(synchronize_session=False)
db.query(Job).filter(Job.fingerprint.like("apt-%")).delete(synchronize_session=False)
db.query(AICache).delete()
db.commit()

now = dt.datetime.now(dt.timezone.utc)
u = User(email="h1b@applytest.example.com", name="Pat Tester", account_type="seeker", plan="free",
         headline="Senior SDET", summary="SDET with 9 years across payments and healthcare.", location="St. Louis, MO",
         phone="555-0100", linkedin="https://linkedin.com/in/pat", work_auth=["h1b"], referral_code="apt-h1b")
other = User(email="other@applytest.example.com", name="Olive Other", account_type="seeker", plan="pro",
             work_auth=["usc"], referral_code="apt-oth")
rec = User(email="rec@applytest.example.com", name="Rae Recruiter", account_type="recruiter", referral_code="apt-rec")
db.add_all([u, other, rec]); db.commit()
db.add_all([
    Position(user_id=u.id, company="Mastercard", role="Senior SDET", started_on=dt.date(2021, 1, 1), location="O'Fallon, MO",
             bullets=["Built Cypress suites for payment portals", "Wrote SQL checks for ETL pipelines",
                      "Cut regression time from 6 hours to 2 hours with parallel Jenkins runs"]),
    Position(user_id=u.id, company="TCS", role="QA Automation Engineer", started_on=dt.date(2017, 1, 1),
             finished_on=dt.date(2020, 12, 1), bullets=["Automated API tests with RestAssured and Java"]),
    Position(user_id=other.id, company="Globex", role="QA Lead", started_on=dt.date(2020, 1, 1), bullets=["Led QA"]),
])
for s in ["Cypress", "SQL", "Java", "RestAssured", "Jenkins", "ETL testing"]:
    db.add(UserSkill(user_id=u.id, skill=s))
db.add(UserSkill(user_id=other.id, skill="Selenium"))
GH_URL = "https://boards.greenhouse.io/acmepay/jobs/4001234"
LV_URL = LV["hostedUrl"]
db.add_all([
    Job(fingerprint="apt-gh", source="greenhouse", source_id="4001234", company="Acme Pay", title="Senior SDET",
        location="Remote - US", active=True, apply_url=GH_URL, required_skills=["Cypress", "SQL", "Kafka"],
        description="<p>Own quality for our payments platform.</p><ul><li>Cypress &amp; SQL</li><li>Kafka a plus</li></ul>"
                    "<script>alert(1)</script>"),
    Job(fingerprint="apt-lv", source="lever", source_id=LV["id"], company="Brightlane", title="QA Automation Engineer",
        location="Remote", active=True, apply_url=LV_URL, required_skills=["Playwright"], description="Plain text JD."),
    Job(fingerprint="apt-ab", source="ashby", source_id="11111111-2222-3333-4444-555555555555", company="Nimbus",
        title="SDET", active=True, apply_url="https://jobs.ashbyhq.com/nimbus/11111111-2222-3333-4444-555555555555"),
])
db.commit()

T_U = tokens.issue(u)["access_token"]
T_O = tokens.issue(other)["access_token"]
T_R = tokens.issue(rec)["access_token"]
H = lambda t: {"Authorization": f"Bearer {t}"}
c = TestClient(app)

print("\nAPPLY\n")

# ── 1. job description ──
r = c.get("/api/jobs/apt-gh")
d = r.json().get("description", "")
ok("job detail returns the description", r.status_code == 200 and "Own quality for our payments platform." in d, d)
ok("  as text: no tags, no script", "<" not in d and "alert" not in d, d)
ok("  entities decoded, list kept as bullets", "• Cypress & SQL" in d and "• Kafka a plus" in d, d)
ok("  plain-text descriptions pass through", c.get("/api/jobs/apt-lv").json()["description"] == "Plain text JD.")

# ── 2. normalisers against recorded fixtures ──
qs = ats.normalize_greenhouse(GH)
by = {q["id"]: q for q in qs}
ok("greenhouse: every visible question, hidden ones dropped", "question_30008" not in by and len(qs) == 16, [q["id"] for q in qs])
ok("  resume is a file (not the resume_text textarea)", by["resume"]["type"] == "file" and by["resume"]["required"], by.get("resume"))
ok("  yes/no select -> boolean", by["question_30002"]["type"] == "boolean" and by["question_30002"]["options"] == ["Yes", "No"])
ok("  single select keeps its options", by["question_30005"]["type"] == "select" and "6-9 years" in by["question_30005"]["options"])
ok("  multi select", by["question_30007"]["type"] == "multi")
ok("  textarea", by["question_30004"]["type"] == "textarea" and by["question_30004"]["required"])
ok("  EEO compliance + demographic flagged eeo", by["gender"]["eeo"] and by["veteran_status"]["eeo"] and by["demographic_7001"]["eeo"])
ok("  non-EEO questions not flagged", not by["question_30003"]["eeo"] and not by["first_name"]["eeo"])
lq = ats.normalize_lever(LV)
ok("lever: the standard documented form", [q["id"] for q in lq][:3] == ["resume", "name", "email"] and any(q["id"] == "urls[LinkedIn]" for q in lq))
ok("lever: a non-posting gives nothing", ats.normalize_lever({}) == [])

j_gh, j_lv, j_ab = db.get(Job, "apt-gh"), db.get(Job, "apt-lv"), db.get(Job, "apt-ab")
ok("ref: greenhouse board + id from apply_url", ats.ref_for(j_gh) == {"ats": "greenhouse", "board": "acmepay", "id": "4001234"})
ok("ref: lever site + id", ats.ref_for(j_lv) == {"ats": "lever", "board": "brightlane", "id": LV["id"]})
ok("ref: ashby recognised", (ats.ref_for(j_ab) or {}).get("ats") == "ashby")


class FakeResp:
    def __init__(self, status, data): self.status_code, self._d = status, data
    def json(self): return self._d


calls = []
real_get = ats.requests.get


def fake_get(url, **kw):
    calls.append(url)
    if "boards-api.greenhouse.io/v1/boards/acmepay/jobs/4001234" in url and kw.get("params", {}).get("questions") == "true":
        return FakeResp(200, GH)
    if url.endswith(f"/postings/brightlane/{LV['id']}"):
        return FakeResp(200, LV)
    raise ats.requests.ConnectionError("no network in tests")


ats.requests.get = fake_get
try:
    r = c.get("/api/jobs/apt-gh/questions", headers=H(T_U))
    g = r.json()
    ok("GET questions: greenhouse supported, normalised", r.status_code == 200 and g["supported"] and g["ats"] == "greenhouse"
       and len(g["questions"]) == 16, g)
    n = len(calls)
    g2 = c.get("/api/jobs/apt-gh/questions", headers=H(T_U)).json()
    ok("  cached: second call makes no request", len(calls) == n and g2.get("cached"), (len(calls), n))
    lv = c.get("/api/jobs/apt-lv/questions", headers=H(T_U)).json()
    ok("GET questions: lever supported, marked partial", lv["supported"] and lv["partial"] and lv["ats"] == "lever", lv)
    ab = c.get("/api/jobs/apt-ab/questions", headers=H(T_U)).json()
    ok("GET questions: ashby -> supported:false, no crash", ab["supported"] is False, ab)
    ok("GET questions needs a sign-in", c.get("/api/jobs/apt-gh/questions", headers=H("junk")).status_code == 401)
    db.query(ATSQuestions).filter(ATSQuestions.fingerprint == "apt-gh").delete(); db.commit()
    ats.requests.get = lambda *a, **k: (_ for _ in ()).throw(ats.requests.Timeout("slow"))
    to = c.get("/api/jobs/apt-gh/questions", headers=H(T_U)).json()
    ok("timeout -> supported:false, and the failure is not cached", to["supported"] is False and db.get(ATSQuestions, "apt-gh") is None, to)
    ats.requests.get = lambda *a, **k: FakeResp(200, {"questions": "garbage"})
    bad = c.get("/api/jobs/apt-gh/questions", headers=H(T_U)).json()
    ok("malformed ATS JSON -> supported:false, no crash", bad["supported"] is False, bad)
finally:
    ats.requests.get = fake_get

# ── 3. pre-fill from the profile ──
db.expire_all()
pos_u = db.query(Position).filter(Position.user_id == u.id).all()
facts = ats.profile_facts(u, pos_u)
ok("facts: years counted from role dates", facts["years"] >= 9, facts["years"])
ok("facts: current company/title from the open role", facts["current_company"] == "Mastercard" and facts["current_title"] == "Senior SDET")
pf = {q["id"]: q for q in ats.prefill(qs, facts)}
ok("prefill: first/last/email/phone from the profile", pf["first_name"]["value"] == "Pat" and pf["last_name"]["value"] == "Tester"
   and pf["email"]["value"] == u.email and pf["phone"]["value"] == "555-0100")
ok("prefill: LinkedIn by label", pf["question_30001"]["value"] == u.linkedin)
ok("prefill: H-1B -> authorized Yes", pf["question_30002"]["value"] == "Yes" and pf["question_30002"]["source"] == "derived")
ok("prefill: H-1B -> sponsorship Yes", pf["question_30003"]["value"] == "Yes", pf["question_30003"])
ok("prefill: years picks the matching range", pf["question_30005"]["value"] in ("6-9 years", "10+ years"), pf["question_30005"])
ok("prefill: custom question left blank and flagged", pf["question_30004"]["value"] == "" and pf["question_30004"]["needs_you"])
ok("prefill: salary left for the user", pf["question_30006"]["value"] == "" and pf["question_30006"]["needs_you"])
ok("prefill: resume -> tailored resume file", pf["resume"]["source"] == "file")
ok("prefill: EEO set to decline, never guessed", pf["gender"]["value"] == "Decline To Self Identify"
   and pf["veteran_status"]["value"] == "I don't wish to answer" and pf["demographic_7001"]["value"] == "I prefer not to answer")
f_usc = ats.profile_facts(other, [])
pfo = {q["id"]: q for q in ats.prefill(qs, f_usc)}
ok("prefill: U.S. citizen -> sponsorship No, authorized Yes", pfo["question_30003"]["value"] == "No" and pfo["question_30002"]["value"] == "Yes")
f_none = {**f_usc, "work_auth": [], "authorized": None, "needs_sponsorship": None}
pfn = {q["id"]: q for q in ats.prefill(qs, f_none)}
ok("prefill: no work authorization on file -> both blank, needs you", pfn["question_30003"]["value"] == "" and pfn["question_30003"]["needs_you"]
   and pfn["question_30002"]["value"] == "")
inv = ats.prefill([{"id": "q9", "label": "Are you authorized to work in the US without sponsorship?", "type": "boolean",
                    "required": True, "options": ["Yes", "No"], "eeo": False}], facts)[0]
ok("prefill: 'authorized without sponsorship?' is answered No for H-1B", inv["value"] == "No", inv)
ck = ats.checklist(list(pf.values()))
ok("checklist counts non-EEO answered, and open required ones", ck["total"] == 13 and ck["required_open"] >= 1 and not ck["ready"], ck)

# ── 4. Apply page: start, save ──
r = c.post("/api/apply/start", json={"fingerprint": "apt-gh"}, headers=H(T_U))
v = r.json()
ok("start: 200 with description, questions and answers", r.status_code == 200 and "Own quality" in v["job"]["description"]
   and v["questions"]["supported"] and len(v["answers"]) == 16, r.text[:300])
app_id = v["application"]["id"]
ok("start: tracker row created as 'opened'", db.get(Application, app_id).status == "opened")
ok("start: a resume ordered for this job exists (no AI, free)", v["resume"] and v["resume"]["ai"] is False and v["resume_cost"] == 1)
ok("  its roles are the profile's, most recent first", [x["company"] for x in v["resume"]["roles"]] == ["Mastercard", "TCS"])
ok("  job's skills lead the skills list", v["resume"]["skills"][:2] == ["Cypress", "SQL"], v["resume"]["skills"])
ok("start: a plain cover letter from profile facts", "Senior SDET" in v["cover_letter"] and "Acme Pay" in v["cover_letter"])
ok("start again: same row", c.post("/api/apply/start", json={"fingerprint": "apt-gh"}, headers=H(T_U)).json()["application"]["id"] == app_id)
r = c.put(f"/api/apply/{app_id}", json={"answers": {"question_30004": "Your payments work is what I do.",
                                                    "question_30006": "Open to discuss"}, "cover_letter": "Edited letter"},
          headers=H(T_U))
ok("save answers", r.status_code == 200 and r.json()["saved"], r.text)
a = db.get(Application, app_id); db.refresh(a)
sa = {q["id"]: q for q in a.answers}
ok("  stored on the Application row", sa["question_30004"]["value"].startswith("Your payments") and sa["question_30004"]["source"] == "you"
   and a.cover_letter == "Edited letter")
ok("save: a choice that isn't an option is refused", c.put(f"/api/apply/{app_id}", json={"answers": {"question_30003": "Maybe"}},
                                                          headers=H(T_U)).status_code == 400)
ok("apply page is owner-only", c.get(f"/api/apply/{app_id}", headers=H(T_O)).status_code == 404
   and c.put(f"/api/apply/{app_id}", json={"cover_letter": "x"}, headers=H(T_O)).status_code == 404)
ok("recruiters can't use it", c.post("/api/apply/start", json={"fingerprint": "apt-gh"}, headers=H(T_R)).status_code == 403)
lvv = c.post("/api/apply/start", json={"fingerprint": "apt-lv"}, headers=H(T_U)).json()
lva = {q["id"]: q for q in lvv["answers"]}
ok("lever start: name/org/LinkedIn prefilled", lva["name"]["value"] == "Pat Tester" and lva["org"]["value"] == "Mastercard"
   and lva["urls[LinkedIn]"]["value"] == u.linkedin, lva.get("org"))
abv = c.post("/api/apply/start", json={"fingerprint": "apt-ab"}, headers=H(T_U)).json()
aba = {q["id"]: q for q in abv["answers"]}
ok("unsupported ATS: standard questions, sponsorship derived", not abv["questions"]["supported"] and aba["sponsorship"]["value"] == "Yes"
   and aba["work_authorized"]["value"] == "Yes")

# ── 5. PDF ──
r = c.get(f"/api/apply/{app_id}/resume.pdf", headers=H(T_U))
ok("resume.pdf: application/pdf, real PDF", r.status_code == 200 and r.headers["content-type"] == "application/pdf"
   and r.content[:4] == b"%PDF" and len(r.content) > 1500, (r.status_code, r.headers.get("content-type"), len(r.content)))
try:
    from pypdf import PdfReader
    import io
    txt = "".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    ok("  contains the name, employers and a bullet", "Pat Tester" in txt and "Mastercard" in txt and "Cypress" in txt, txt[:200])
    ok("  one or two pages", len(PdfReader(io.BytesIO(r.content)).pages) <= 2)
except ImportError:
    pass
ok("resume.pdf is owner-only", c.get(f"/api/apply/{app_id}/resume.pdf", headers=H(T_O)).status_code == 404)
ok("resume.pdf refuses a bad token", c.get(f"/api/apply/{app_id}/resume.pdf", headers=H("junk")).status_code == 401)

# ── 6. tailored resume validation ──
def good():
    return {"summary": "Senior SDET with 9 years in payments QA using Cypress and SQL.",
            "roles": [{"id": "P1", "bullets": ["Built Cypress suites for payment portals used by card teams",
                                               "Cut regression time from 6 hours to 2 hours with parallel Jenkins runs"]},
                      {"id": "P2", "bullets": ["Automated API tests with RestAssured and Java"]}],
            "skills": ["Cypress", "SQL", "Java"],
            "cover_letter": "Dear Acme Pay team,\n\nYour Senior SDET role matches the payments quality work I do with Cypress and SQL.\n\nThank you."}


res, why = R.check_ai(good(), u, pos_u, ["Cypress", "SQL", "Java", "RestAssured", "Jenkins", "ETL testing"], j_gh)
ok("check_ai accepts a faithful draft", res is not None, why)
if res:
    rr = res[0]
    ok("  employers, titles and dates come from the profile", rr["roles"][0]["company"] == "Mastercard" and rr["roles"][0]["dates"].startswith("Jan 2021")
       and rr["roles"][1]["role"] == "QA Automation Engineer")
    ok("  every profile skill kept, relevant first", rr["skills"][:3] == ["Cypress", "SQL", "Java"] and "ETL testing" in rr["skills"])
SK = ["Cypress", "SQL", "Java", "RestAssured", "Jenkins", "ETL testing"]
for label, mut in [
    ("an employer we never gave it", lambda g: g["roles"].append({"id": "P9", "bullets": ["Worked at Google"]})),
    ("a skill not on the profile", lambda g: g["skills"].append("Kafka")),
    ("a tool in a bullet not on the profile", lambda g: g["roles"][0]["bullets"].append("Built Kafka consumers for settlement events")),
    ("an invented number", lambda g: g["roles"][0]["bullets"].append("Raised coverage to 95% across 40 services")),
    ("an invented number in the summary", lambda g: g.__setitem__("summary", "SDET with 15 years of experience.")),
    ("a placeholder", lambda g: g.__setitem__("cover_letter", "Dear [Hiring Manager],\n\n" + "x" * 100)),
    ("a tool in the cover letter not on the profile", lambda g: g.__setitem__("cover_letter", "I have used Kafka and Terraform daily. " * 4)),
]:
    g = good(); mut(g)
    res2, why2 = R.check_ai(g, u, pos_u, SK, j_gh)
    ok(f"check_ai rejects {label}", res2 is None, why2)


# ── 7. tailor endpoint: credits, rejection, caching ──
calls_ai = []
orig_call = AI._call
AI._call = lambda prompt, *a, **k: (calls_ai.append(prompt), good())[1]
try:
    before = db.get(User, u.id); db.refresh(before); used0 = before.credits_used or 0
    r = c.post(f"/api/apply/{app_id}/resume", headers=H(T_U))
    ok("tailor: 200 and an AI resume", r.status_code == 200 and r.json()["resume"]["ai"] is True, r.text[:200])
    ok("  the prompt carried only profile facts + the job", "Mastercard" in calls_ai[-1] and "Globex" not in calls_ai[-1])
    db.refresh(before)
    ok("  on-demand (not Autopilot) costs one credit", (before.credits_used or 0) == used0 + 1, (before.credits_used, used0))
    ok("  the AI cover letter replaces the letter", r.json()["cover_letter"].startswith("Dear Acme Pay team"))
    r = c.post(f"/api/apply/{app_id}/resume", headers=H(T_U))
    db.refresh(before)
    ok("  same profile + job again: served from cache, free", r.status_code == 200 and (before.credits_used or 0) == used0 + 1 and len(calls_ai) == 1)
    AI._call = lambda prompt, *a, **k: {**good(), "skills": ["Cypress", "Kubernetes"]}
    lv_id = lvv["application"]["id"]
    r = c.post(f"/api/apply/{lv_id}/resume", headers=H(T_U))
    db.refresh(before)
    ok("tailor: invented facts -> 422, nothing charged", r.status_code == 422 and (before.credits_used or 0) == used0 + 1, (r.status_code, r.text[:150]))
    ok("  the stored resume is still the no-AI one", db.get(Application, lv_id).tailored_resume["resume"]["ai"] is False)
    from fastapi import HTTPException

    def down(*a, **k): raise HTTPException(503, "AI is busy right now.")
    AI._call = down
    r = c.post(f"/api/apply/{lv_id}/resume", headers=H(T_U))
    db.refresh(before)
    ok("tailor: AI down -> 503, nothing charged", r.status_code == 503 and (before.credits_used or 0) == used0 + 1)
    # Autopilot items were paid for by the preparation
    ap_app = Application(user_id=u.id, fingerprint="apt-ab", company="Nimbus", title="SDET", status="ready", origin="autopilot",
                         cover_letter="Prepared letter " * 8, tailored_resume={"summary": "s", "highlights": ["h"]})
    db.query(Application).filter(Application.user_id == u.id, Application.fingerprint == "apt-ab").delete()
    db.add(ap_app); db.commit()
    AI._call = lambda prompt, *a, **k: good()
    view = c.post("/api/apply/start", json={"application_id": ap_app.id}, headers=H(T_U)).json()
    ok("autopilot item: tailoring is free", view["resume_cost"] == 0 and view["cover_letter"].startswith("Prepared letter"), view["resume_cost"])
    r = c.post(f"/api/apply/{ap_app.id}/resume", headers=H(T_U))
    db.refresh(before)
    ok("  generated without spending a credit", r.status_code == 200 and (before.credits_used or 0) == used0 + 1, (r.status_code, before.credits_used))
    ok("  regenerating after that costs one", r.json()["resume_cost"] == 1)
    r = c.post(f"/api/apply/{ap_app.id}/handoff", headers=H(T_U))
    db.refresh(ap_app)
    ok("handoff: an autopilot item leaves the queue as opened, not applied", r.status_code == 200 and ap_app.status == "opened"
       and ap_app.applied_at is None)
finally:
    AI._call = orig_call

# ── 8. extension key ──
r = c.post("/api/auth/extension-token", headers=H(T_U))
ext = r.json().get("token", "")
ok("extension-token: issued to a signed-in seeker", r.status_code == 200 and ext and r.json()["scope"] == "extension")
ok("  not without a session", c.post("/api/auth/extension-token", headers=H("junk")).status_code == 401)
ok("  refused by /api/profile", c.get("/api/profile", headers=H(ext)).status_code == 401)
ok("  refused by /api/applications", c.get("/api/applications", headers=H(ext)).status_code == 401)
ok("  refused by the Apply page API", c.get(f"/api/apply/{app_id}", headers=H(ext)).status_code == 401)
ok("  refused by AI endpoints", c.post(f"/api/apply/{app_id}/resume", headers=H(ext)).status_code == 401)
ok("  can't mint another key", c.post("/api/auth/extension-token", headers=H(ext)).status_code == 401)
r = c.get(f"/api/apply-packet?application_id={app_id}", headers=H(ext))
pk = r.json()
ok("apply-packet with the extension key", r.status_code == 200 and pk["application_id"] == app_id and pk["profile"]["email"] == u.email
   and any(x["id"] == "question_30004" and x["value"].startswith("Your payments") for x in pk["answers"])
   and pk["files"]["resume_pdf"] == f"/api/apply/{app_id}/resume.pdf" and pk["cover_letter"], r.text[:200])
ok("apply-packet without an application: profile only", set(c.get("/api/apply-packet", headers=H(ext)).json()) == {"profile"})
ok("resume.pdf with the extension key", c.get(f"/api/apply/{app_id}/resume.pdf", headers=H(ext)).content[:4] == b"%PDF")
ok("apply-packet is owner-only", c.get(f"/api/apply-packet?application_id={app_id}", headers=H(T_O)).status_code == 404)
ext_o = c.post("/api/auth/extension-token", headers=H(T_O)).json()["token"]
ok("  another user's extension key can't read it", c.get(f"/api/apply-packet?application_id={app_id}", headers=H(ext_o)).status_code == 404
   and c.get(f"/api/apply/{app_id}/resume.pdf", headers=H(ext_o)).status_code == 404)
r = c.post(f"/api/apply/{app_id}/report", json={"status": "filled", "filled": 9, "needs_you": 2}, headers=H(ext))
ok("report filled: recorded, NOT applied", r.status_code == 200 and db.get(Application, app_id).applied_at is None
   and r.json()["status"] == "opened")
ok("report: unknown status refused", c.post(f"/api/apply/{app_id}/report", json={"status": "sent"}, headers=H(ext)).status_code == 400)
r = c.post(f"/api/apply/{app_id}/report", json={"status": "applied"}, headers=H(ext))
db.expire_all()
ok("report applied (the user's own button): submitted", r.status_code == 200 and db.get(Application, app_id).status == "submitted")
ok("revoke", c.delete("/api/auth/extension-token", headers=H(T_U)).json()["revoked"] >= 1)
ok("  a revoked key stops working at once", c.get(f"/api/apply-packet?application_id={app_id}", headers=H(ext)).status_code == 401)
ok("  the other user's key is untouched", c.get("/api/apply-packet", headers=H(ext_o)).status_code == 200)
forged = tokens.issue_extension(u, "not-a-real-jti")["token"]
ok("  a key whose id isn't on file is refused", c.get("/api/apply-packet", headers=H(forged)).status_code == 401)

# ── 9. Autopilot preparation carries the tailored resume (same single AI call) ──
db.query(Application).filter(Application.user_id == u.id).delete(); db.commit()
j_ap = Job(fingerprint="apt-ap", source="aptest", company="Orbit", title="Senior SDET", active=True, apply_url="https://x.test/apt-ap",
           required_skills=["Cypress"], description="Cypress and SQL.", first_seen=now, posted_at=now)
j_ap2 = Job(fingerprint="apt-ap2", source="aptest", company="Orbit2", title="Senior SDET II", active=True, apply_url="https://x.test/apt-ap2",
            required_skills=["Cypress"], description="Cypress and SQL.", first_seen=now, posted_at=now)
db.add_all([j_ap, j_ap2]); db.commit()
draft = {"subject": "Senior SDET — Pat Tester", "summary": "SDET focused on Cypress and SQL for payments.",
         "highlights": ["Built Cypress suites for payment portals"],
         "cover_letter": "Dear Orbit team,\n\nI build Cypress suites for payment portals and write SQL checks for ETL pipelines. I'd like to do that for you.\n\nThanks.",
         "resume": {"roles": [{"id": "P1", "bullets": ["Built Cypress suites for payment portals"]}], "skills": ["Cypress", "SQL"]}}
orig_call = AI._call
AI._call = lambda *a, **k: json.loads(json.dumps(draft))
try:
    profile, _ = AP._profile_block(db, u)
    ok("autopilot prompt ids the roles for the resume", "P1: Senior SDET at Mastercard" in profile, profile[:200])
    a1, why = AP._prepare_one(db, u, j_ap, profile)
    ok("autopilot draft stores a validated tailored resume", a1 is not None and a1.tailored_resume["resume"]["ai"] is True
       and a1.tailored_resume["resume"]["roles"][0]["company"] == "Mastercard" and a1.tailored_resume["highlights"], why)
    ok("  and marks it as already paid for", (a1.form_fields or {}).get("ai_resume_done") is True)
    bad = json.loads(json.dumps(draft)); bad["resume"]["skills"] = ["Kubernetes"]
    AI._call = lambda *a, **k: bad
    a2, why = AP._prepare_one(db, u, j_ap2, profile)
    ok("autopilot: an invalid resume is dropped but the draft is still queued", a2 is not None and "resume" not in a2.tailored_resume, why)
finally:
    AI._call = orig_call

ats.requests.get = real_get
# Leave nothing behind: other test files may share this database (Postgres CI).
db.rollback()
uids = [x.id for x in db.query(User).filter(User.email.like("%@applytest.example.com"))]
for M in (ExtensionToken, Application, AutopilotRun, AutopilotConfig):
    db.query(M).filter(M.user_id.in_(uids)).delete(synchronize_session=False)
db.query(ATSQuestions).filter(ATSQuestions.fingerprint.like("apt-%")).delete(synchronize_session=False)
db.query(Job).filter(Job.fingerprint.like("apt-%")).delete(synchronize_session=False)
for x in db.query(User).filter(User.id.in_(uids)).all():
    db.delete(x)
db.commit()
db.close()
print(f"\n{'=' * 48}\nPASS {P}    FAIL {F}")
for f in fails:
    print("  ✗", f)
print("ALL GREEN" if not F else "")
sys.exit(1 if F else 0)
