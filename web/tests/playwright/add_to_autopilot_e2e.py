"""Real-browser end-to-end for "Add to Autopilot" + the free allowance (not part of run-all.sh).

Runs everything itself, against throwaway state:
  * a stub OpenAI-compatible AI server on a local port (no network, no real model),
  * jobs written through the real ingest upsert path (ingest.run.ingest_batch),
  * the real FastAPI app (ENV=dev, DATABASE_URL=sqlite:///./qa_free.db, wiped first),
  * web/ served statically, with config.js overridden by request interception
    (nothing in the repo changes).
A brand-new FREE account is created through the sign-up screen, gets a resume through the
profile page, adds 5 different jobs from Explore Jobs, hits the upgrade prompt on the 6th,
approves one, reloads, is then upgraded to Pro directly in the DB, and uses the scheduled
Autopilot toggle and Add to Autopilot again.

    python3 web/tests/playwright/add_to_autopilot_e2e.py            (from the repo root)

Chromium comes from /opt/pw-browsers (override with CHROME=...). Screenshots (1280px and
390px) go to $SHOTS (default: a temp dir) and are printed at the end.
"""
import datetime as dt, glob, json, os, shutil, sqlite3, subprocess, sys, tempfile, threading, time, urllib.request, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SERVER, WEB = os.path.join(ROOT, "server"), os.path.join(ROOT, "web")
DBFILE = os.path.join(SERVER, "qa_free.db")
API_PORT, WEB_PORT, AI_PORT = 8017, 8087, 9911
API, SITE = f"http://127.0.0.1:{API_PORT}", f"http://127.0.0.1:{WEB_PORT}/index.html"
CHROME = os.environ.get("CHROME") or glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")[0]
SHOTS = os.environ.get("SHOTS") or tempfile.mkdtemp(prefix="ap_shots_")
os.makedirs(SHOTS, exist_ok=True)
P = F = 0


def ok(name, cond, extra=""):
    global P, F
    if cond: P += 1; print("  ok  ", name)
    else: F += 1; print("  FAIL", name, extra)


# ── stub AI: OpenAI-compatible /chat/completions ────────────────────────────
STUB = {"fail": 0, "calls": 0}


class AI(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        STUB["calls"] += 1
        if STUB["fail"] > 0:
            STUB["fail"] -= 1
            self.send_response(503); self.end_headers(); self.wfile.write(b'{"error":"overloaded"}'); return
        prompt = body["messages"][-1]["content"]
        role = prompt.split("ROLE:", 1)[1].split("\n", 1)[0].strip() if "ROLE:" in prompt else "this role"
        title, _, rest = role.partition(" at ")
        company = rest.split(" (")[0]
        bullets = [l.strip()[2:].strip() for l in prompt.splitlines() if l.strip().startswith("•")][:4] or ["Built automated test suites"]
        out = {"subject": f"{title} — Test Candidate",
               "summary": f"Automation-focused QA engineer whose recent work maps directly onto {title} at {company}.",
               "highlights": bullets,
               "cover_letter": f"Dear {company} team,\n\nI am applying for the {title} role. My recent work has been building and maintaining automated test suites, "
                               f"and the responsibilities in your posting line up closely with it.\n\nI would welcome the chance to talk through how that experience applies at {company}.\n\nThank you for your time."}
        payload = json.dumps({"choices": [{"message": {"content": json.dumps(out)}}]}).encode()
        self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers(); self.wfile.write(payload)


# ── data ────────────────────────────────────────────────────────────────────
JOBS = [  # company, title, description, host
    ("Northwind Payments", "Senior SDET", "Own our Cypress and Playwright suites for card-processing services. Java, REST API testing, CI/CD with GitHub Actions.", "careers.northwindpayments.com"),
    ("Cobalt Health", "QA Automation Engineer", "Build Selenium and Cypress automation for our claims platform. API testing with Postman, Java, SQL, Agile.", "jobs.cobalthealth.com"),
    ("Lumen Retail", "Test Automation Lead", "Lead automation for e-commerce checkout: Playwright, TypeScript, CI/CD, performance testing.", "careers.lumenretail.com"),
    ("Tidewater Insurance", "SDET II", "Java, TestNG, Maven, RestAssured, API testing and ETL testing for policy systems.", "jobs.tidewaterinsurance.com"),
    ("Brightline Bank", "Software Engineer in Test", "Cypress, JavaScript, API testing, Jenkins CI/CD for retail banking apps.", "careers.brightlinebank.com"),
    ("Meridian Cloud", "Quality Engineer", "Selenium, Java, SQL, AWS, Agile QA on a SaaS platform.", "jobs.meridiancloud.com"),
    ("Harbor Logistics", "QA Engineer", "Manual and automated testing, Postman, SQL, Jira.", "careers.harborlogistics.com"),
    ("Ardent Labs", "Senior QA Automation Engineer", "Playwright, Cypress, CI/CD. We are unable to sponsor H-1B or any other work visas; candidates must be authorized to work in the U.S. without sponsorship.", "careers.ardentlabs.com"),
]
VISIBLE = lambda: [c for c in JOBS if c[0] != "Ardent Labs"]      # with H-1B set on the profile, a posting that excludes H-1B is hidden by the board's own filter
RESUME = """Test Candidate
Senior QA Automation Engineer / SDET
St. Louis, MO

EXPERIENCE

Senior SDET - Mastercard, St. Louis, MO
Jan 2021 - Present
• Built Cypress and Playwright suites for payment workflows and API testing with Postman and RestAssured
• Ran regression and integration testing in Jenkins CI/CD pipelines on AWS
• Wrote SQL checks for ETL testing of transaction data

QA Automation Engineer - Humana, Louisville, KY
Mar 2018 - Dec 2020
• Automated web and API tests with Selenium, Java, TestNG and Maven
• Performed functional, regression and performance testing on claims applications

SKILLS
Cypress, Playwright, Selenium, Java, JavaScript, TypeScript, SQL, Postman, RestAssured, TestNG, Maven, Jenkins, CI/CD, AWS, Agile, API testing, ETL testing
"""


def seed():
    for f in glob.glob(DBFILE + "*"): os.remove(f)
    code = f"""
import os, sys, datetime as dt
sys.path.insert(0, os.getcwd())
from api.db import init_db, SessionLocal
from ingest import run
init_db(); db = SessionLocal(); now = dt.datetime.now(dt.timezone.utc)
recs = []
for i, (co, ti, desc, host) in enumerate({JOBS!r}):
    recs.append(dict(source="greenhouse", source_id=str(1000 + i), company=co, title=ti, location="Remote (US)", description=desc,
                     url=f"https://{{host}}/jobs/{{1000 + i}}", posted_at=(now - dt.timedelta(days=i)).isoformat()))
print(run.ingest_batch(db, recs, now, run.WANTED_LOOSE))
from api.models import Job
from api.auth import _dev_user
_dev_user(db)      # dev mode signs anonymous callers in as this user; create it now so two parallel first requests can't race to insert it
print("jobs:", db.query(Job).count())
"""
    env = {**os.environ, "ENV": "dev", "DATABASE_URL": "sqlite:///./qa_free.db"}
    r = subprocess.run([sys.executable, "-c", code], cwd=SERVER, env=env, capture_output=True, text=True)
    print(r.stdout.strip()[-200:], r.stderr.strip()[-300:] if r.returncode else "")
    assert r.returncode == 0 and "jobs: 8" in r.stdout, r.stderr


def wait_http(url, secs=30):
    end = time.time() + secs
    while time.time() < end:
        try: urllib.request.urlopen(url, timeout=2); return True
        except Exception: time.sleep(0.4)
    return False


def db_get(sql, *a):
    c = sqlite3.connect(DBFILE); try_ = c.execute(sql, a).fetchall(); c.close(); return try_


def token(pg):
    return json.loads(pg.evaluate("localStorage.getItem('cp_token')") or '""')


def api(pg, path, method="GET", body=None):
    r = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
        headers={"content-type": "application/json", "Authorization": "Bearer " + token(pg)})
    try:
        with urllib.request.urlopen(r) as f: return f.status, json.loads(f.read() or b"null")
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b"null")


def new_page(b, width, height=900, tok=None):
    ctx = b.new_context(viewport={"width": width, "height": height})
    ctx.route("**/config.js", lambda r: r.fulfill(body='window.CP_CONFIG={api:"%s"};' % API, content_type="application/javascript"))
    # The employers' sites don't exist in this sandbox: answer their apply URLs locally so the popup URL can be read.
    ctx.route(lambda u: u.startswith("https://") and "/jobs/" in u and "127.0.0.1" not in u,
              lambda r: r.fulfill(body="<h1>Posting</h1>", content_type="text/html"))
    if tok: ctx.add_init_script("try{localStorage.setItem('cp_token',JSON.stringify(%s))}catch(e){}" % json.dumps(tok))
    return ctx, ctx.new_page()


def cards(pg): return pg.locator("#list .job")
def card(pg, company): return pg.locator("#list .job", has_text=company)


def apadd_text(pg, company):
    return card(pg, company).locator(".apadd").inner_text().replace("\n", " | ")


def main():
    seed()
    ai = ThreadingHTTPServer(("127.0.0.1", AI_PORT), AI); threading.Thread(target=ai.serve_forever, daemon=True).start()
    env = {**os.environ, "ENV": "dev", "DATABASE_URL": "sqlite:///./qa_free.db", "AI_BASE_URL": f"http://127.0.0.1:{AI_PORT}",
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
        for f in glob.glob(DBFILE + "*"): pass       # qa_free.db is git-ignored; left for inspection
    print(f"\nPASS {P}    FAIL {F}\nscreenshots: {SHOTS}")
    sys.exit(1 if F else 0)


def run_flow():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"])
        ctx, pg = new_page(b, 1280)
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        adds = []
        pg.on("request", lambda r: adds.append(r) if r.method == "POST" and r.url.endswith("/api/autopilot/add-job") else None)

        print("\n── signed out ──")
        pg.goto(SITE); pg.wait_for_selector("#list .job", timeout=15000)
        ok("all 8 jobs are listed", cards(pg).count() == 8, cards(pg).count())
        ok("every card has Add to Autopilot", pg.locator("#list .job .apadd button", has_text="Add to Autopilot").count() == 8)
        card(pg, "Northwind").locator(".apadd button").click(); pg.wait_for_timeout(500)
        ok("signed out: click opens the sign-in screen, sends nothing", pg.locator("#authGate.on").count() == 1 and not adds)

        print("\n── sign up a real FREE account through the UI ──")
        email = f"e2e{uuid.uuid4().hex[:8]}@careerpilot-test.com"
        pg.click("#authTabUp"); pg.fill("#au-name", "Test Candidate"); pg.fill("#au-email", email); pg.fill("#au-pass", "Zx9!kq-Plum-73")
        pg.click("#authGo"); pg.wait_for_function("document.getElementById('authGate').classList.contains('on')===false", timeout=15000)
        pg.wait_for_timeout(1200)
        ok("account created, plan is free (DB)", db_get("select plan from users where email=?", email) == [("free",)])

        print("\n── profile: resume + work authorization ──")
        pg.evaluate("go('me')"); pg.wait_for_timeout(300)
        pg.set_input_files("#rfile", {"name": "resume.txt", "mimeType": "text/plain", "buffer": RESUME.encode()})
        pg.wait_for_selector("#afterUpload", state="visible", timeout=15000)
        pg.select_option("#p-auth", "h1b"); pg.wait_for_timeout(300)
        for _ in range(40):                                        # the profile push is debounced; wait for the server to hold it
            s, prof = api(pg, "/api/profile")
            if s == 200 and prof.get("positions") and prof.get("skills") and (prof.get("work_auth") or []): break
            pg.wait_for_timeout(500)
        ok("server holds positions, skills and work authorization", bool(prof.get("positions")) and len(prof.get("skills", [])) >= 5 and "h1b" in (prof.get("work_auth") or []), prof)

        print("\n── Explore Jobs: buttons + counter, straight from the server ──")
        pg.evaluate("go('jobs')"); pg.wait_for_timeout(300)
        pg.reload(); pg.wait_for_selector("#list .job", timeout=15000); pg.wait_for_timeout(1500)
        ok("every card: Add to Autopilot + '5 of 5 free left'", all("Add to Autopilot" in apadd_text(pg, c[0]) and "5 of 5 free left" in apadd_text(pg, c[0]) for c in VISIBLE()), [apadd_text(pg, c[0]) for c in VISIBLE()][:2])
        ok("the board hides the posting that excludes H-1B (7 shown)", cards(pg).count() == 7, cards(pg).count())
        pg.screenshot(path=os.path.join(SHOTS, "01_jobs_1280.png"))
        card(pg, "Northwind").click(position={"x": 60, "y": 20}); pg.wait_for_timeout(500)
        ok("job detail shows the button too", pg.locator('#jobDetailPane .apadd[data-apctx="detail"]').count() == 1 and "5 of 5 free left" in pg.locator('#jobDetailPane .apadd').inner_text())
        pg.screenshot(path=os.path.join(SHOTS, "02_detail_1280.png"))

        print("\n── errors first: a job that excludes H-1B, then an AI failure ──")
        pg.select_option("#f-auth", "any"); pg.wait_for_selector("#list .job:has-text('Ardent')", timeout=10000); pg.wait_for_timeout(600)
        card(pg, "Ardent").locator(".apadd button").click(); pg.wait_for_timeout(1200)
        t = apadd_text(pg, "Ardent")
        ok("H-1B-excluded job: plain-English refusal, button back, counter untouched", "won't accept H-1B" in t and "Add to Autopilot" in t and "5 of 5 free left" in t, t)
        pg.screenshot(path=os.path.join(SHOTS, "03_error_1280.png"))
        pg.select_option("#f-auth", "h1b"); pg.wait_for_timeout(1000)
        STUB["fail"] = 5
        card(pg, "Northwind").locator(".apadd button").click(); pg.wait_for_timeout(2500)
        t = apadd_text(pg, "Northwind")
        ok("AI failure: says it's busy and that nothing was used; still 5 of 5", "busy" in t.lower() and "Nothing was used" in t and "5 of 5 free left" in t, t)
        ok("  DB: nothing spent, nothing queued", db_get("select coalesce(free_used,0) from autopilot_configs") == [(0,)] and db_get("select count(*) from applications") == [(0,)])
        STUB["fail"] = 0

        print("\n── add 5 different jobs ──")
        added = []
        for co in ["Northwind", "Cobalt", "Lumen", "Tidewater", "Brightline"]:
            for attempt in range(60):                              # the AI breaker (45s) may still be open after the failures above
                card(pg, co).locator(".apadd button").click()
                pg.wait_for_function("(c)=>{const el=[...document.querySelectorAll('#list .job')].find(x=>x.textContent.includes(c));const a=el&&el.querySelector('.apadd');return a&&!/Preparing/.test(a.textContent)}", arg=co, timeout=60000)
                if "In your Autopilot queue" in apadd_text(pg, co): break
                pg.wait_for_timeout(3000)
            added.append(co)
            ok(f"{co}: 'In your Autopilot queue'", "In your Autopilot queue" in apadd_text(pg, co), apadd_text(pg, co))
        ok("five queued, free_used = 5, no generation credit spent (DB)",
           db_get("select coalesce(free_used,0) from autopilot_configs") == [(5,)] and db_get("select count(*) from applications where origin='autopilot' and status='ready'") == [(5,)]
           and db_get("select coalesce(credits_used,0) from users where email=?", email) == [(0,)])
        left = [c for c in VISIBLE() if c[0].split()[0] not in added]
        ok("the remaining 2 jobs now offer 'Upgrade for more Autopilot' with an honest message",
           all("Upgrade for more Autopilot" in apadd_text(pg, c[0]) and "used your 5 free Autopilot applications" in apadd_text(pg, c[0]) for c in left), [apadd_text(pg, c[0]) for c in left])
        pg.screenshot(path=os.path.join(SHOTS, "04_exhausted_1280.png"))
        n_before = len(adds)
        card(pg, "Meridian").locator(".apadd button").click(); pg.wait_for_timeout(700)
        ok("the 6th click goes to the plan page and calls no API", pg.evaluate("document.getElementById('p-plan').classList.contains('on')") and len(adds) == n_before)
        ok("  plan page: Free lists 5 Autopilot applications; Pro lists Scheduled Autopilot",
           "5 Autopilot applications" in pg.locator(".pricecard").nth(0).inner_text() and "Scheduled Autopilot" in pg.locator(".pricecard").nth(1).inner_text())
        pg.screenshot(path=os.path.join(SHOTS, "05_plan_1280.png"), full_page=True)
        s, r = api(pg, "/api/autopilot/add-job", "POST", {"fingerprint": db_get("select fingerprint from jobs where company='Meridian Cloud'")[0][0]})
        ok("server enforces it independently: a direct API call gets 402", s == 402 and "Upgrade" in r["detail"], (s, r))

        print("\n── the Autopilot page as a free account; approve one ──")
        pg.evaluate("go('autopilot')"); pg.wait_for_selector("#ap-queue .apqueue", timeout=10000); pg.wait_for_timeout(800)
        ok("shows 'You've used your 5 free Autopilot applications' and the upgrade button", "used your 5 free Autopilot applications" in pg.inner_text("#ap-free") and "Upgrade for more Autopilot" in pg.inner_text("#ap-free"), pg.inner_text("#ap-free"))
        ok("  explains scheduled Autopilot is Pro", "Pro" in pg.inner_text("#ap-free"))
        ok("  queue lists all 5 and stays usable", pg.locator("#ap-queue .apqueue").count() == 5)
        ok("  Setup / run-history cards are hidden for free", not pg.locator("#p-autopilot [data-sched]").first.is_visible())
        pg.screenshot(path=os.path.join(SHOTS, "06_autopilot_free_1280.png"), full_page=True)
        pg.locator("#ap-queue .apqueue").first.locator("button", has_text="Preview").click(); pg.wait_for_selector("#md .mb", timeout=5000)
        ok("Preview shows the tailored cover letter", "Dear" in pg.inner_text("#md .mb") and "Cover letter" in pg.inner_text("#md .mb"))
        pg.keyboard.press("Escape"); pg.evaluate("closeM()"); pg.wait_for_timeout(200)
        first_title = pg.locator("#ap-queue .apqueue b").first.inner_text()
        with ctx.expect_page(timeout=8000) as popup:
            pg.locator("#ap-queue .apqueue").first.locator("button", has_text="Approve").click()
        url = popup.value.url
        ok("Approve just opens the real apply_url (nothing is sent)", url.startswith("https://") and "/jobs/" in url, url)
        popup.value.close(); pg.wait_for_timeout(800)
        ok("  approved item left the queue; 4 remain", pg.locator("#ap-queue .apqueue").count() == 4)
        approved_co = [c[0] for c in VISIBLE() if c[1] == first_title][0]

        print("\n── reload: state persists from the server ──")
        pg.evaluate("go('jobs')"); pg.reload(); pg.wait_for_selector("#list .job", timeout=15000); pg.wait_for_timeout(1500)
        states = {c[0]: apadd_text(pg, c[0]) for c in VISIBLE()}
        ok("approved job says 'Approved in Autopilot'", "Approved in Autopilot" in states[approved_co], states[approved_co])
        ok("the other 4 say 'In your Autopilot queue'", sum("In your Autopilot queue" in v for k, v in states.items() if k != approved_co) == 4, states)
        ok("the rest still say Upgrade for more Autopilot", sum("Upgrade for more Autopilot" in v for v in states.values()) == 2)
        pg.evaluate("go('autopilot')"); pg.wait_for_timeout(1200)
        ok("Autopilot page after reload: still 0 left, 4 in queue", "used your 5 free" in pg.inner_text("#ap-free") and pg.locator("#ap-queue .apqueue").count() == 4)
        ok("  no client-only state: the counter is the server's (5 of 5 used in DB)", db_get("select free_used from autopilot_configs") == [(5,)])

        print("\n── upgrade to Pro directly in the DB ──")
        c = sqlite3.connect(DBFILE); c.execute("update users set plan='pro' where email=?", (email,)); c.commit(); c.close()
        pg.evaluate("go('jobs')"); pg.reload(); pg.wait_for_selector("#list .job", timeout=15000); pg.wait_for_timeout(1800)
        states = {c[0]: apadd_text(pg, c[0]) for c in VISIBLE()}
        ok("Pro: no counter anywhere, no upgrade prompts", not any("free left" in v or "Upgrade" in v for v in states.values()), states)
        ok("  the 2 remaining jobs are addable again ('Add to Autopilot')", sum(v.startswith("Add to Autopilot") for v in states.values()) == 2, states)
        pg.evaluate("go('autopilot')"); pg.wait_for_timeout(1200)
        ok("Autopilot page for Pro: free card hidden, scheduled controls visible", not pg.locator("#ap-free").is_visible() and pg.locator("#ap-flightplan").is_visible() and pg.locator("#p-autopilot [data-sched]").first.is_visible())
        pg.screenshot(path=os.path.join(SHOTS, "07_autopilot_pro_1280.png"), full_page=True)
        pg.locator("#ap-checklist button", has_text="Confirm resume").click(); pg.wait_for_timeout(800)
        pg.locator(".apslider").click(); pg.wait_for_timeout(2500)
        ok("scheduled Autopilot toggle switches on for Pro", pg.is_checked("#ap-on") and db_get("select \"on\" from autopilot_configs") == [(1,)], pg.evaluate("document.getElementById('toast').textContent"))
        pg.wait_for_function("!document.getElementById('ap-prog') || document.getElementById('ap-prog').hidden || !/working/i.test(document.getElementById('ap-prog-title').textContent)", timeout=90000)
        pg.reload(); pg.wait_for_timeout(1500); pg.evaluate("go('autopilot')"); pg.wait_for_timeout(1200)
        ok("  and stays on after a reload", pg.is_checked("#ap-on"))
        pg.evaluate("go('jobs')"); pg.wait_for_selector("#list .job", timeout=15000); pg.wait_for_timeout(1200)
        target = next(c[0] for c in VISIBLE() if apadd_text(pg, c[0]).startswith("Add to Autopilot"))
        used_before = db_get("select coalesce(credits_used,0) from users where email=?", email)[0][0]
        card(pg, target).locator(".apadd button").click(); pg.wait_for_function("(c)=>{const el=[...document.querySelectorAll('#list .job')].find(x=>x.textContent.includes(c));const a=el&&el.querySelector('.apadd');return a&&!/Preparing/.test(a.textContent)}", arg=target, timeout=60000)
        pg.wait_for_timeout(300)
        ok(f"Pro: Add to Autopilot still works ({target})", "In your Autopilot queue" in apadd_text(pg, target), apadd_text(pg, target))
        ok("  it used a generation credit and never touched the free counter",
           db_get("select coalesce(credits_used,0) from users where email=?", email)[0][0] > used_before and db_get("select free_used from autopilot_configs") == [(5,)])
        pg.screenshot(path=os.path.join(SHOTS, "08_jobs_pro_1280.png"))
        ok("no uncaught page errors", not errors, errors[:3])
        ctx.close()

        print("\n── 390px (phone) ──")
        # A second FREE account (fresh allowance) so the phone view shows the counter state. Its profile is
        # written through the real profile API; the phone checks below are all in the browser.
        email2 = f"e2e{uuid.uuid4().hex[:8]}@careerpilot-test.com"
        def call(m, path, body, tok=None):
            r = urllib.request.Request(API + path, method=m, data=json.dumps(body).encode(),
                                      headers={"content-type": "application/json", **({"Authorization": "Bearer " + tok} if tok else {})})
            return json.loads(urllib.request.urlopen(r).read() or b"null")
        tok2 = call("POST", "/api/auth/signup", {"email": email2, "password": "Zx9!kq-Plum-73", "name": "Phone Person", "account_type": "seeker"})["access_token"]
        call("POST", "/api/positions", {"company": "Acme", "role": "SDET", "started_on": "2019-01-01", "bullets": ["Built Cypress suites for payment APIs"]}, tok2)
        call("PUT", "/api/profile/skills", {"skills": ["Cypress", "Java", "API testing", "Playwright"]}, tok2)
        ctx2, pm = new_page(b, 390, 844, tok=tok2)
        pm.goto(SITE); pm.wait_for_selector("#list .job", timeout=15000); pm.wait_for_timeout(2000)
        ok("390px: no horizontal page scroll", pm.evaluate("document.documentElement.scrollWidth<=window.innerWidth+1"), pm.evaluate("[document.documentElement.scrollWidth,window.innerWidth]"))
        overflow = pm.evaluate("""[...document.querySelectorAll('#list .job')].filter(j=>{const r=j.getBoundingClientRect();return [...j.querySelectorAll('.cardacts *')].some(e=>{const b=e.getBoundingClientRect();return b.right>r.right+1||b.left<r.left-1})}).length""")
        ok("390px: nothing in any card's action row overflows the card", overflow == 0, overflow)
        ok("390px: every card shows the button with '5 of 5 free left'", pm.locator("#list .job .apadd button", has_text="Add to Autopilot").count() == 8 and "5 of 5 free left" in apadd_text(pm, "Northwind"), apadd_text(pm, "Northwind"))
        pm.screenshot(path=os.path.join(SHOTS, "09_jobs_390.png"))
        pm.wait_for_timeout(2500)          # let the post-sign-in job reload settle before an element screenshot
        card(pm, "Northwind").screenshot(path=os.path.join(SHOTS, "10_card_390.png"))
        card(pm, "Northwind").locator(".apadd button").focus(); pm.keyboard.press("Enter")
        pm.wait_for_function("(c)=>{const el=[...document.querySelectorAll('#list .job')].find(x=>x.textContent.includes(c));const a=el&&el.querySelector('.apadd');return a&&/In your Autopilot queue|busy|Add your skills/i.test(a.textContent)}", arg="Northwind", timeout=60000)
        ok("390px: Enter on the button adds the job (keyboard) and does not also open the detail",
           "In your Autopilot queue" in apadd_text(pm, "Northwind") and not pm.locator("#md").evaluate("e=>e.closest('.modal,.overlay')?getComputedStyle(e.closest('.modal,.overlay')).display!=='none' && e.closest('.modal,.overlay').classList.contains('on'):false"), apadd_text(pm, "Northwind"))
        ok("  counter dropped to 4 of 5 on the other cards", "4 of 5 free left" in apadd_text(pm, "Cobalt"), apadd_text(pm, "Cobalt"))
        pm.screenshot(path=os.path.join(SHOTS, "11_jobs_390_after.png"))
        card(pm, "Cobalt").locator("button", has_text="Details").click(); pm.wait_for_timeout(600)
        ok("390px: the job detail (modal) has the button", pm.locator('#md .apadd[data-apctx="detail"]').count() == 1)
        pm.screenshot(path=os.path.join(SHOTS, "12_detail_390.png"))
        pm.evaluate("closeM()"); pm.evaluate("go('autopilot')"); pm.wait_for_timeout(1200)
        ok("390px: Autopilot page has no horizontal scroll", pm.evaluate("document.documentElement.scrollWidth<=window.innerWidth+1"), pm.evaluate("[document.documentElement.scrollWidth,window.innerWidth]"))
        pm.screenshot(path=os.path.join(SHOTS, "13_autopilot_390.png"), full_page=True)
        ctx2.close(); b.close()


if __name__ == "__main__":
    main()
