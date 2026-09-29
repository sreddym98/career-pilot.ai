# Regression: a signed-in seeker left idle must send NO requests (the old save loop sent ~2/s and
# exhausted the Neon free-tier compute quota). Needs: API on :8011 (ENV=dev) with a few jobs, web/ served on :3011.
import json, time, requests
from playwright.sync_api import sync_playwright
API="http://localhost:8011"
r=requests.post(API+"/api/auth/signup",json={"email":f"loop{int(time.time())}@example.com","password":"Str0ng!pass9-x","name":"Loop Test","account_type":"seeker"})
tok=r.json()["access_token"]
H={"Authorization":"Bearer "+tok}
requests.put(API+"/api/profile/skills",headers=H,json={"skills":["Cypress","Java"]})
print(requests.post(API+"/api/positions",headers=H,json={"company":"Mastercard","role":"Senior SDET","started_on":"2020-01-01","bullets":["Built Cypress suites"]}).status_code)
with sync_playwright() as p:
    b=p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
    pg=b.new_page()
    pg.route("**/config.js", lambda rt: rt.fulfill(body='window.CP_CONFIG={api:"%s"};'%API, content_type="application/javascript"))
    pg.add_init_script("localStorage.setItem('cp_token', JSON.stringify(%s))" % json.dumps(tok))
    reqs=[]
    pg.on("request", lambda q: reqs.append((time.time(), q.method, q.url.replace(API,""))) if q.url.startswith(API) else None)
    pg.goto("http://localhost:3011/index.html"); pg.wait_for_timeout(6000)
    t0=time.time(); pg.wait_for_timeout(20000)
    idle=[x for x in reqs if x[0]>=t0]
    print("requests in 20s idle:", len(idle), [ (m,u.split('?')[0]) for _,m,u in idle][:12])
    # now edit something and ensure exactly one save cycle
    pg.evaluate("document.getElementById('p-phone') && (document.getElementById('p-phone').value='+1 555 111 2222', document.getElementById('p-phone').dispatchEvent(new Event('input',{bubbles:true})), document.getElementById('p-phone').dispatchEvent(new Event('change',{bubbles:true})))")
    t1=time.time(); pg.wait_for_timeout(25000)
    after=[(m,u.split('?')[0]) for t,m,u in reqs if t>=t1]
    print("25s after one edit:", len(after), after[:8])
    b.close()
