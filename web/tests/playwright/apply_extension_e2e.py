"""Real-browser end-to-end for the Apply page + the unpacked extension (not part of run-all.sh).

Runs everything itself, against throwaway state:
  * a stub OpenAI-compatible AI server on a local port (no network, no real model),
  * jobs written through the real ingest upsert path, with apply links on Greenhouse and Lever,
  * the employer's public question schema pre-cached from recorded fixtures (server/fixtures/)
    exactly as api/ats.py stores a live fetch (the live ATS hosts aren't reachable here),
  * the real FastAPI app (ENV=dev, DATABASE_URL=sqlite:///./qa_onsite.db, wiped first),
  * web/ served statically, config.js overridden by request interception (nothing in the repo changes),
  * Chromium with extension/ loaded unpacked (persistent context, new headless),
  * the employer pages answered LOCALLY by fixture HTML (web/tests/playwright/fixtures/) that mimics a
    Greenhouse and a Lever application form, with a submit handler that only counts submissions.

    python3 web/tests/playwright/apply_extension_e2e.py            (from the repo root)
"""
import glob, json, os, shutil, sqlite3, subprocess, sys, tempfile, threading, time, urllib.request, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SERVER, WEB, EXT = os.path.join(ROOT, "server"), os.path.join(ROOT, "web"), os.path.join(ROOT, "extension")
DBFILE = os.path.join(SERVER, "qa_onsite.db")
API_PORT, WEB_PORT, AI_PORT = 8031, 8093, 9931
API, SITE = f"http://127.0.0.1:{API_PORT}", f"http://127.0.0.1:{WEB_PORT}/index.html"
CHROME = os.environ.get("CHROME") or glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")[0]
SHOTS = os.environ.get("SHOTS") or tempfile.mkdtemp(prefix="apply_shots_")
os.makedirs(SHOTS, exist_ok=True)
GH_URL = "https://boards.greenhouse.io/acmepay/jobs/4001234"
LV_ID = "5b0c2d4e-8f1a-4c3b-9d2e-7a6f5e4d3c2b"
LV_URL = f"https://jobs.lever.co/brightlane/{LV_ID}"
P = F = 0


def ok(name, cond, extra=""):
    global P, F
    if cond: P += 1; print("  ok  ", name)
    else: F += 1; print("  FAIL", name, str(extra)[:300])


# ── stub AI: echoes the candidate's own facts back as a "tailored" draft ─────
class AI(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")
        prompt = body["messages"][-1]["content"]
        roles, cur, skills = [], None, []
        for line in prompt.splitlines():
            s = line.strip()
            if not s or s.startswith("JOB:"):
                cur = None
            if len(s) > 3 and s[0] == "P" and s[1].isdigit() and ":" in s[:4]:
                cur = {"id": s.split(":", 1)[0], "bullets": []}; roles.append(cur)
            elif cur is not None and s.startswith("- "):
                cur["bullets"].append(s[2:])
            elif s.startswith("Skills:"):
                skills = [x.strip() for x in s[7:].split(",") if x.strip()]
        for r in roles: r["bullets"] = list(reversed(r["bullets"]))
        out = {"summary": "QA engineer who builds Cypress and Playwright suites for payment workflows.",
               "roles": roles, "skills": list(reversed(skills)),
               "cover_letter": "Dear hiring team,\n\nI build Cypress and Playwright suites for payment workflows, and your role is that work.\n\nI would welcome a conversation.\n\nThank you."}
        payload = json.dumps({"choices": [{"message": {"content": json.dumps(out)}}]}).encode()
        self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers(); self.wfile.write(payload)


def seed():
    for f in glob.glob(DBFILE + "*"): os.remove(f)
    code = f"""
import os, sys, json, datetime as dt
sys.path.insert(0, os.getcwd())
from api.db import init_db, SessionLocal
from api.models import Job, ATSQuestions
from api import ats
from ingest import run
init_db(); db = SessionLocal(); now = dt.datetime.now(dt.timezone.utc)
recs = [dict(source="greenhouse", source_id="4001234", company="Acme Pay", title="Senior SDET", location="Remote (US)",
             description="<p>Own quality for our payments platform with Cypress and Playwright.</p><h3>What you'll do</h3><ul><li>Automate API tests</li><li>Write SQL checks</li></ul>",
             url={GH_URL!r}, posted_at=now.isoformat()),
        dict(source="lever", source_id={LV_ID!r}, company="Brightlane", title="QA Automation Engineer", location="Remote",
             description="Build and run our Playwright suites. Java, SQL, CI/CD.", url={LV_URL!r}, posted_at=now.isoformat())]
print(run.ingest_batch(db, recs, now, run.WANTED_LOOSE))
gh = json.load(open("fixtures/greenhouse_job_questions.json")); lv = json.load(open("fixtures/lever_posting.json"))
for j in db.query(Job).all():
    if "greenhouse" in (j.apply_url or ""):
        res = {{"supported": True, "ats": "greenhouse", "partial": False, "questions": ats.normalize_greenhouse(gh)}}
    else:
        res = {{"supported": True, "ats": "lever", "partial": True, "questions": ats.normalize_lever(lv)}}
    db.merge(ATSQuestions(fingerprint=j.fingerprint, result=res, fetched_at=now))
db.commit()
print("jobs:", db.query(Job).count())
"""
    env = {**os.environ, "ENV": "dev", "DATABASE_URL": "sqlite:///./qa_onsite.db"}
    r = subprocess.run([sys.executable, "-c", code], cwd=SERVER, env=env, capture_output=True, text=True)
    print(r.stdout.strip()[-200:], r.stderr.strip()[-600:] if r.returncode else "")
    assert r.returncode == 0 and "jobs: 2" in r.stdout, r.stderr


def wait_http(url, secs=30):
    end = time.time() + secs
    while time.time() < end:
        try: urllib.request.urlopen(url, timeout=2); return True
        except Exception: time.sleep(0.4)
    return False


def call(path, method="GET", body=None, tok=None):
    r = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                               headers={"content-type": "application/json", **({"Authorization": "Bearer " + tok} if tok else {})})
    try:
        with urllib.request.urlopen(r) as f: return f.status, json.loads(f.read() or b"null")
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b"null")


def db_get(sql, *a):
    c = sqlite3.connect(DBFILE); rows = c.execute(sql, a).fetchall(); c.close(); return rows


def make_user():
    email = f"apply{uuid.uuid4().hex[:6]}@careerpilot-test.com"
    s, d = call("/api/auth/signup", "POST", {"email": email, "password": "Zx9!kq-Plum-73", "name": "Test Candidate", "account_type": "seeker"})
    assert s == 201, d
    tok = d["access_token"]
    call("/api/profile", "PUT", {"phone": "314-555-0100", "location": "St. Louis, MO", "linkedin": "https://linkedin.com/in/test-candidate",
                                 "headline": "Senior SDET", "summary": "QA engineer focused on payment systems.", "work_auth": ["h1b"]}, tok)
    call("/api/positions", "POST", {"company": "Mastercard", "role": "Senior SDET", "started_on": "2021-01-01", "location": "O'Fallon, MO",
                                    "bullets": ["Built Cypress and Playwright suites for payment workflows", "Wrote SQL checks for ETL pipelines"]}, tok)
    call("/api/positions", "POST", {"company": "Humana", "role": "QA Automation Engineer", "started_on": "2016-03-01", "finished_on": "2020-12-01",
                                    "bullets": ["Automated API tests with Java and RestAssured"]}, tok)
    call("/api/profile/skills", "PUT", {"skills": ["Cypress", "Playwright", "SQL", "Java", "RestAssured", "CI/CD"], "top": ["Cypress"]}, tok)
    return email, tok


def main():
    seed()
    ai = ThreadingHTTPServer(("127.0.0.1", AI_PORT), AI); threading.Thread(target=ai.serve_forever, daemon=True).start()
    env = {**os.environ, "ENV": "dev", "DATABASE_URL": "sqlite:///./qa_onsite.db", "AI_BASE_URL": f"http://127.0.0.1:{AI_PORT}",
           "AI_API_KEY": "stub", "AI_PROVIDER": "openai", "AI_MODEL": "stub-model", "AI_FAST_MODEL": "stub-fast",
           "CRON_SECRET": "", "PYTHONUNBUFFERED": "1", "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}
    apisrv = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.main:app", "--port", str(API_PORT), "--log-level", "warning"],
                              cwd=SERVER, env=env, stdout=open(os.path.join(SHOTS, "api.log"), "w"), stderr=subprocess.STDOUT)
    web = subprocess.Popen([sys.executable, "-m", "http.server", str(WEB_PORT), "--bind", "127.0.0.1"], cwd=WEB,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert wait_http(API + "/health") and wait_http(SITE), "servers did not start"
        run_flow()
    finally:
        apisrv.terminate(); web.terminate(); ai.shutdown()
    print(f"\nPASS {P}    FAIL {F}\nscreenshots: {SHOTS}")
    sys.exit(1 if F else 0)


def overlay_text(pg):
    return pg.evaluate("(()=>{const h=document.getElementById('cp-overlay');return h&&h.shadowRoot?h.shadowRoot.querySelector('.box').innerText:''})()")


def run_flow():
    email, tok = make_user()
    fixture = lambda name: open(os.path.join(HERE, "fixtures", name), encoding="utf-8").read()
    employer_posts = []
    udd = tempfile.mkdtemp(prefix="cp_ext_profile_")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            udd, executable_path=CHROME, headless=True, viewport={"width": 1280, "height": 900}, accept_downloads=True,
            args=["--headless=new", f"--disable-extensions-except={EXT}", f"--load-extension={EXT}", "--no-sandbox",
                  "--proxy-server=direct://", "--proxy-bypass-list=*"])
        ctx.route("**/config.js", lambda r: r.fulfill(body='window.CP_CONFIG={api:"%s"};' % API, content_type="application/javascript"))

        def employer(route):
            req = route.request
            if req.method != "GET":
                employer_posts.append(req.url)
                return route.fulfill(status=200, body="received", content_type="text/plain")
            if "greenhouse.io" in req.url:
                return route.fulfill(body=fixture("greenhouse_apply.html"), content_type="text/html")
            return route.fulfill(body=fixture("lever_apply.html"), content_type="text/html")
        ctx.route("https://boards.greenhouse.io/**", employer)
        ctx.route("https://jobs.lever.co/**", employer)
        ctx.add_init_script("try{if(location.port==='%d')localStorage.setItem('cp_token',JSON.stringify(%s))}catch(e){}" % (WEB_PORT, json.dumps(tok)))

        sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker", timeout=15000)
        ok("extension loaded (service worker up)", "background.js" in sw.url, sw.url)

        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(SITE); pg.wait_for_selector("#list .job", timeout=20000); pg.wait_for_timeout(1500)
        ok("bridge announced itself on the site", pg.evaluate("document.documentElement.getAttribute('data-careerpilot-ext')") == "1.2.0")

        print("\n── job detail: the description ──")
        pg.locator("#list .job", has_text="Acme Pay").click(position={"x": 60, "y": 20}); pg.wait_for_timeout(1200)
        jd = pg.locator("#jdBox").inner_text()
        ok("job detail shows the description", "Own quality for our payments platform" in jd and "No description available" not in jd, jd[:120])
        ok("  HTML turned into readable text (bullets, no tags)", "Automate API tests" in jd and "<li>" not in jd, jd[:200])
        pg.screenshot(path=os.path.join(SHOTS, "01_detail.png"))

        print("\n── Apply page ──")
        pg.get_by_role("button", name="Apply with CareerPilot").first.click()
        pg.wait_for_selector("#apl-ready", timeout=15000); pg.wait_for_timeout(500)
        md = pg.locator("#md")
        ok("Apply page opens with the checklist", "Ready:" in pg.locator("#apl-ready").inner_text(), pg.locator("#apl-ready").inner_text())
        q = lambda qid: md.locator(f'.aplq[data-qid="{qid}"]')
        ok("  first name pre-answered", q("first_name").locator("input").input_value() == "Test")
        ok("  LinkedIn pre-answered", q("question_30001").locator("input").input_value() == "https://linkedin.com/in/test-candidate")
        ok("  sponsorship pre-answered from H-1B", q("question_30003").locator("select").input_value() == "Yes")
        ok("  work authorization pre-answered", q("question_30002").locator("select").input_value() == "Yes")
        ok("  years picked from role dates", q("question_30005").locator("select").input_value() in ("6-9 years", "10+ years"),
           q("question_30005").locator("select").input_value())
        ok("  custom question flagged 'you answer this'", "You answer this" in q("question_30004").inner_text()
           and q("question_30004").locator("textarea").input_value() == "")
        pg.screenshot(path=os.path.join(SHOTS, "02_apply_1280.png"), full_page=True)

        ok("a full-page resize doesn't close the Apply page", pg.evaluate("document.getElementById('ov').classList.contains('on')"))
        with pg.expect_download() as dl:
            md.get_by_role("button", name="Download resume PDF").first.click()
        path = dl.value.path(); data = open(path, "rb").read()
        ok("tailored resume PDF downloads (non-empty, %PDF)", data[:4] == b"%PDF" and len(data) > 1500, (data[:8], len(data)))

        md.get_by_role("button", name="Tailor with AI · 1 generation").click()
        pg.wait_for_function("document.querySelector('#md') && /Tailored to this job/.test(document.querySelector('#md').textContent)", timeout=20000)
        ok("Tailor with AI: rewritten from the profile, one credit", "Tailored to this job" in md.inner_text()
           and db_get("select credits_used from users where email=?", email) == [(1,)], db_get("select credits_used from users where email=?", email))

        q("question_30004").locator("textarea").fill("I test payment systems for a living and Acme Pay is where that matters most.")
        md.locator("#apl-cl").fill("Dear Acme Pay team,\n\nI build Cypress suites for payment workflows.\n\nThanks,\nTest Candidate")
        pg.wait_for_timeout(1200)
        ans = json.loads(db_get("select answers from applications where fingerprint in (select fingerprint from jobs where company='Acme Pay')")[0][0])
        ok("edited answer saved on the Application row", any(a["id"] == "question_30004" and a["value"].startswith("I test payment") for a in ans))
        ok("  cover letter edit saved", db_get("select cover_letter from applications where company='Acme Pay'")[0][0].startswith("Dear Acme Pay team"))

        print("\n── connect the extension ──")
        pg.wait_for_selector("#apl-connect", timeout=5000)
        md.get_by_role("button", name="Connect extension").click()
        pg.wait_for_selector("#apl-extok", timeout=8000)
        ok("Connect extension: connected via the page", "Extension connected" in md.inner_text())
        stored = sw.evaluate("chrome.storage.local.get(['extToken','apiBase'])")
        ok("  the extension holds a scoped key and the API address", bool(stored.get("extToken")) and stored.get("apiBase") == API, stored.get("apiBase"))
        ok("  the key is scoped: /api/profile refuses it", call("/api/profile", tok=stored.get("extToken"))[0] == 401)
        ok("  copy on the send button", "You'll click Submit on Acme Pay's page. We fill it in; we never submit for you." in md.inner_text())

        print("\n── Send to employer: Greenhouse-like form ──")
        with ctx.expect_page(timeout=15000) as newp:
            md.get_by_role("button", name="Send to employer").click()
        emp = newp.value
        emp.wait_for_load_state()
        emp.wait_for_function("!!document.getElementById('cp-overlay')", timeout=20000)
        emp.wait_for_timeout(500)
        v = lambda sel: emp.eval_on_selector(sel, "e=>e.value")
        ok("employer page is the posting", emp.url.startswith(GH_URL), emp.url)
        ok("filled: name, email, phone", v("#first_name") == "Test" and v("#last_name") == "Candidate" and v("#email") == email
           and v("#phone") == "314-555-0100", [v("#first_name"), v("#last_name"), v("#email"), v("#phone")])
        ok("filled: LinkedIn (custom question id)", v("#question_30001") == "https://linkedin.com/in/test-candidate")
        ok("filled: authorization + sponsorship selects", v("#question_30002") == "1" and v("#question_30003") == "1",
           [v("#question_30002"), v("#question_30003")])
        ok("filled: your own answer to the custom question", v("#question_30004").startswith("I test payment"))
        ok("filled: years", v("#question_30005") in ("13", "14"), v("#question_30005"))
        rf = emp.evaluate("(()=>{const f=document.getElementById('resume').files[0];return f?{name:f.name,size:f.size,type:f.type}:null})()")
        ok("resume attached (input.files[0])", rf and rf["name"].endswith(".pdf") and rf["size"] > 1000 and rf["type"] == "application/pdf", rf)
        cf = emp.evaluate("(()=>{const f=document.getElementById('cover_letter').files[0];return f?{name:f.name,size:f.size}:null})()")
        ok("cover letter attached", cf and cf["size"] > 20, cf)
        ok("EEO left as decline", v("#gender") == "3" and v("#veteran_status") == "3"
           and emp.evaluate("document.querySelector('input[name=\"demographic_7001[]\"][value=\"3\"]').checked"))
        ok("salary left blank", v("#question_30006") == "")
        ot = overlay_text(emp)
        ok("overlay: lists what was filled", "CareerPilot filled" in ot and "First Name" in ot, ot[:200])
        ok("overlay: lists needs-you items (unknown required question, salary)", "How did you hear about us?" in ot and "salary" in ot.lower(), ot)
        ok("overlay: ends with review-and-submit, never submits", "Review everything, then click Submit on this page. We never submit for you." in ot)
        ok("unfilled required field highlighted", emp.eval_on_selector("#question_39999", "e=>e.classList.contains('cp-needs')"))
        ok("NOT submitted: zero submissions, zero submit clicks, no POST to the employer",
           emp.evaluate("window.__submits") == 0 and emp.evaluate("window.__submitClicks") == 0 and not employer_posts,
           (emp.evaluate("window.__submits"), emp.evaluate("window.__submitClicks"), employer_posts))
        emp.screenshot(path=os.path.join(SHOTS, "03_greenhouse_filled.png"), full_page=True)
        time.sleep(1)
        row = db_get("select status, applied_at, form_fields from applications where company='Acme Pay'")[0]
        ok("server: 'filled' recorded, status opened, NOT applied", row[0] == "opened" and row[1] is None and "filled_at" in (row[2] or ""), row[:2])
        emp.evaluate("document.getElementById('cp-overlay').shadowRoot.getElementById('cp-done').click()")
        emp.wait_for_timeout(1500)
        ok("'I submitted it' (pressed by the user) marks it applied", db_get("select status from applications where company='Acme Pay'") == [("submitted",)],
           db_get("select status from applications where company='Acme Pay'"))
        ok("  still zero submissions on the employer page", emp.evaluate("window.__submits") == 0 and not employer_posts)
        emp.close()

        print("\n── Send to employer: Lever-like form ──")
        pg.bring_to_front()
        pg.evaluate("closeM()"); pg.wait_for_timeout(300)
        fp_lv = db_get("select fingerprint from jobs where company='Brightlane'")[0][0]
        pg.evaluate(f"openApplyPage({json.dumps(fp_lv)})"); pg.wait_for_selector("#apl-ready", timeout=15000); pg.wait_for_timeout(600)
        ok("Lever: standard questions pre-answered (name, current company)", q("name").locator("input").input_value() == "Test Candidate"
           and q("org").locator("input").input_value() == "Mastercard")
        with ctx.expect_page(timeout=15000) as newp:
            md.get_by_role("button", name="Send to employer").click()
        emp = newp.value
        emp.wait_for_load_state()
        emp.wait_for_function("!!document.getElementById('cp-overlay')", timeout=20000)
        emp.wait_for_timeout(500)
        ok("opened Lever's form (/apply)", emp.url == LV_URL + "/apply", emp.url)
        n = lambda nm: emp.eval_on_selector(f'[name="{nm}"]', "e=>e.value")
        ok("filled: name, email, phone, location, company, LinkedIn", n("name") == "Test Candidate" and n("email") == email and n("phone") == "314-555-0100"
           and n("location") == "St. Louis, MO" and n("org") == "Mastercard" and n("urls[LinkedIn]") == "https://linkedin.com/in/test-candidate",
           [n("name"), n("org"), n("urls[LinkedIn]")])
        rf = emp.evaluate("(()=>{const f=document.querySelector('input[name=resume]').files[0];return f?{name:f.name,size:f.size}:null})()")
        ok("resume attached", rf and rf["size"] > 1000, rf)
        ot = overlay_text(emp)
        ok("needs you: the custom authorization radio Lever doesn't publish", "Are you legally authorized to work in the United States?" in ot, ot)
        ok("NOT submitted", emp.evaluate("window.__submits") == 0 and emp.evaluate("window.__submitClicks") == 0 and not employer_posts)
        emp.screenshot(path=os.path.join(SHOTS, "04_lever_filled.png"), full_page=True)
        emp.close()

        print("\n── 390px ──")
        pg.bring_to_front()
        pg.set_viewport_size({"width": 390, "height": 844}); pg.wait_for_timeout(500)
        fp_gh = db_get("select fingerprint from jobs where company='Acme Pay'")[0][0]
        pg.evaluate(f"openApplyPage({json.dumps(fp_gh)})"); pg.wait_for_selector("#apl-ready", timeout=15000); pg.wait_for_timeout(600)
        sw_ = pg.evaluate("document.documentElement.scrollWidth")
        box = pg.locator("#md").bounding_box()
        ok("Apply page fits a 390px screen (no sideways scroll)", sw_ <= 390 and box and box["x"] >= 0 and box["x"] + box["width"] <= 391, (sw_, box))
        pg.locator("#apl-go").scroll_into_view_if_needed()
        gb = pg.locator("#apl-go").bounding_box()
        ok("  Send button reachable and full width", pg.locator("#apl-go").is_visible() and gb and gb["x"] >= 0 and gb["x"] + gb["width"] <= 390, gb)
        ok("  questions stack in one column", all((pg.locator(".aplq input, .aplq select, .aplq textarea").nth(i).bounding_box() or {"x": 0, "width": 0})["x"]
                                                 + (pg.locator(".aplq input, .aplq select, .aplq textarea").nth(i).bounding_box() or {"width": 0})["width"] <= 390
                                                 for i in range(min(8, pg.locator(".aplq input, .aplq select, .aplq textarea").count()))))
        pg.screenshot(path=os.path.join(SHOTS, "05_apply_390.png"), full_page=True)
        ok("no page errors", not errors, errors)
        ctx.close()
    shutil.rmtree(udd, ignore_errors=True)


if __name__ == "__main__":
    main()
