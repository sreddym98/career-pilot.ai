"""Real-browser regression check for the Autopilot on/off switch (not part of run-all.sh).

Needs: dev API on :8000 (cd server; ENV=dev DATABASE_URL=sqlite:///./qa_ap.db python seed.py;
uvicorn api.main:app --port 8000), and web/ served on :8080 (python -m http.server 8080).
config.js is overridden by request interception, so nothing in the repo changes.
Set CHROME=/path/to/chrome if not under /opt/pw-browsers. The dev DB is edited directly to make
the account Pro, so run it against a throwaway sqlite file only.
"""
import glob, json, os, sqlite3, sys, uuid, urllib.request
from playwright.sync_api import sync_playwright

API, WEB = "http://localhost:8000", "http://localhost:8080/index.html"
DB = os.environ.get("AP_DB", os.path.join(os.path.dirname(__file__), "..", "..", "..", "server", "qa_ap.db"))
CHROME = os.environ.get("CHROME") or glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")[0]
P = F = 0
def ok(name, cond, extra=""):
    global P, F
    if cond: P += 1
    else: F += 1; print("  FAIL", name, extra)

def call(m, p, b=None, tok=None):
    r = urllib.request.Request(API + p, method=m, data=json.dumps(b).encode() if b is not None else None,
        headers={"content-type": "application/json", **({"Authorization": "Bearer " + tok} if tok else {})})
    try:
        with urllib.request.urlopen(r) as f: return f.status, json.loads(f.read() or b"null")
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b"null")

def account(plan, resume):
    email = f"pw{uuid.uuid4().hex[:8]}@example.com"
    s, r = call("POST", "/api/auth/signup", {"email": email, "password": "Zx9!kq-Plum-73", "name": "PW", "account_type": "seeker"})
    tok = r["access_token"]
    c = sqlite3.connect(DB); c.execute("update users set plan=? where email=?", (plan, email)); c.commit()
    if resume:
        call("POST", "/api/positions", {"company": "Acme", "role": "SDET", "started_on": "2020-01-01", "bullets": ["x"]}, tok)
        call("POST", "/api/autopilot/confirm-resume", tok=tok)
    return tok

def page(b, tok, slow_run=False):
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.route("**/config.js", lambda r: r.fulfill(body='window.CP_CONFIG={api:"%s"};' % API, content_type="application/javascript"))
    pg.add_init_script("""localStorage.setItem('cp_token',JSON.stringify('%s'));
      const _f=window.fetch;window.fetch=async function(u,o){ if(%s&&/autopilot\\/run/.test(u)) await new Promise(r=>setTimeout(r,6000)); return _f.apply(this,arguments)}""" % (tok, "true" if slow_run else "false"))
    pg.goto(WEB); pg.wait_for_timeout(1800); pg.evaluate("go('autopilot')"); pg.wait_for_timeout(1000)
    return pg
toast = lambda pg: pg.evaluate("document.getElementById('toast').textContent")

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"])
    # 1. OFF must work while the first run is still in flight; state survives a reload
    pg = page(b, account("pro", True), slow_run=True)
    pg.locator(".apslider").click(); pg.wait_for_timeout(1500)
    ok("on", pg.is_checked("#ap-on"))
    pg.locator(".apslider").click(); pg.wait_for_timeout(800)
    ok("OFF during run is honoured", not pg.is_checked("#ap-on") and "paused" in pg.inner_text("#ap-toggle-label"), toast(pg))
    pg.wait_for_timeout(6500)
    ok("stays off after the run returns", not pg.is_checked("#ap-on"))
    pg.reload(); pg.wait_for_timeout(1800); pg.evaluate("go('autopilot')"); pg.wait_for_timeout(1000)
    ok("off after reload", not pg.is_checked("#ap-on"))
    pg.locator(".apslider").click(); pg.wait_for_timeout(1500)
    pg.reload(); pg.wait_for_timeout(1800); pg.evaluate("go('autopilot')"); pg.wait_for_timeout(1000)
    ok("on persists after reload", pg.is_checked("#ap-on"))
    # 2. Free plan: honest message + upgrade page
    pg = page(b, account("free", False))
    pg.locator(".apslider").click(); pg.wait_for_timeout(600)
    ok("free: says Pro, no setup detour", "Pro" in toast(pg) and "setup" not in toast(pg).lower(), toast(pg))
    ok("  lands on the plan page", "on" in pg.evaluate("document.getElementById('p-plan').className"))
    # 3. Pro, resume not confirmed: names only the resume (phone isn't required without Twilio)
    pg = page(b, account("pro", False))
    pg.locator(".apslider").click(); pg.wait_for_timeout(600)
    ok("pro/no resume: bounces back with a clear reason", not pg.is_checked("#ap-on") and "confirm your resume" in toast(pg) and "phone" not in toast(pg).lower(), toast(pg))
    b.close()
print(f"PASS {P}    FAIL {F}"); sys.exit(1 if F else 0)
