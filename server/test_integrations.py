"""Gmail OAuth wiring — everything that doesn't require Google to answer.

The parts worth pinning are the ones a live round trip would never exercise:
what happens before credentials are configured, and whether the `state`
parameter can be forged. state is the only thing tying Google's callback back
to a user, and that callback arrives with no session of ours attached — so if
it can be tampered with, anyone can attach their mailbox to someone else's
account.
"""
import os, sys, time, base64
os.environ.setdefault("DATABASE_URL", "sqlite:///./integrations_test.db")
os.environ.setdefault("ENV", "dev")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

P = F = 0; fails = []
def ok(n, c, x=""):
    global P, F
    if c: P += 1
    else: F += 1; fails.append(f"{n}  →  {x}")

def raises(status, fn, *a, **k):
    from fastapi import HTTPException
    try:
        fn(*a, **k); return False, "no exception raised"
    except HTTPException as e:
        return e.status_code == status, f"got {e.status_code}: {e.detail}"

from api.db import init_db, SessionLocal
from api.models import User, Integration
from api.settings import settings
import api.routers.integrations as I
init_db()
db = SessionLocal()

for u in db.query(User).filter(User.email.like("%@integtest.example.com")).all():
    db.delete(u)
db.commit()
user = User(email="sam@integtest.example.com", name="Sam", account_type="seeker",
            referral_code="integ1")
db.add(user); db.commit(); db.refresh(user)

print("\n╔═══ GMAIL INTEGRATION ═══╗\n")

print("── Before it's configured ──")
saved = (settings.GMAIL_CLIENT_ID, settings.GMAIL_CLIENT_SECRET, settings.INTEGRATION_ENCRYPTION_KEY)
settings.GMAIL_CLIENT_ID = settings.GMAIL_CLIENT_SECRET = ""
ok("reports itself unconfigured", I._configured_gmail() is False)
st = I.status(user, db)
ok("  status says so rather than erroring", st["gmail"]["configured"] is False)
ok("  and reports not connected", st["gmail"]["connected"] is False)
m, d = raises(503, I.gmail_start, user)
ok("  starting the flow is refused with a 503", m, d)
ok("  and the message says what to set",
   "GMAIL_CLIENT_ID" in d, d)

print("\n── Once configured ──")
settings.GMAIL_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
settings.GMAIL_CLIENT_SECRET = "test-secret"
if not settings.INTEGRATION_ENCRYPTION_KEY:
    from cryptography.fernet import Fernet
    settings.INTEGRATION_ENCRYPTION_KEY = Fernet.generate_key().decode()
ok("reports itself configured", I._configured_gmail() is True)

url = I.gmail_start(user)["authorization_url"]
ok("hands back a Google consent URL", url.startswith(I.GOOGLE_AUTHORIZE_URL), url[:60])
ok("  asks only for send permission, not full mailbox access",
   "gmail.send" in url and "gmail.readonly" not in url and "mail.google.com" not in url)
ok("  requests offline access, or there's no refresh token to store",
   "access_type=offline" in url)
ok("  forces the consent screen so a refresh token is actually returned",
   "prompt=consent" in url)
ok("  carries our client id", "test-client-id" in url)
ok("  and the registered redirect", "redirect_uri=" in url)

print("\n── The state parameter is the whole security story ──")
import urllib.parse as up
state = up.parse_qs(up.urlparse(url).query)["state"][0]
ok("state resolves back to the user who started it",
   I._user_from_state(state, db).id == user.id)

# Flip one character of the signature.
raw = base64.urlsafe_b64decode(state.encode()).decode()
body, sig = raw.rsplit(":", 1)
forged = base64.urlsafe_b64encode(f"{body}:{'0'*len(sig)}".encode()).decode()
m, d = raises(400, I._user_from_state, forged, db)
ok("a forged signature is rejected", m, d)

# Same signature, different user id — the attack that matters: attaching your
# mailbox to someone else's account.
victim = User(email="victim@integtest.example.com", name="V", referral_code="integ2")
db.add(victim); db.commit(); db.refresh(victim)
parts = raw.split(":")
swapped = base64.urlsafe_b64encode(":".join([victim.id] + parts[1:]).encode()).decode()
m, d = raises(400, I._user_from_state, swapped, db)
ok("swapping in another user's id is rejected", m, d)

m, d = raises(400, I._user_from_state, "not-even-base64!!", db)
ok("garbage state is rejected", m, d)
m, d = raises(400, I._user_from_state, base64.urlsafe_b64encode(b"a:b:c:d").decode(), db)
ok("well-formed but unsigned state is rejected", m, d)

# Expiry: forge a correctly-signed state with an old timestamp.
import hmac as _h, hashlib as _hh
old_payload = f"{user.id}:{int(time.time()) - 601}:nonce"
old_sig = _h.new(settings.INTEGRATION_ENCRYPTION_KEY.encode(), old_payload.encode(), _hh.sha256).hexdigest()
expired = base64.urlsafe_b64encode(f"{old_payload}:{old_sig}".encode()).decode()
m, d = raises(400, I._user_from_state, expired, db)
ok("a correctly-signed but stale state is rejected", m, d)

fresh_payload = f"{user.id}:{int(time.time()) - 60}:nonce"
fresh_sig = _h.new(settings.INTEGRATION_ENCRYPTION_KEY.encode(), fresh_payload.encode(), _hh.sha256).hexdigest()
fresh = base64.urlsafe_b64encode(f"{fresh_payload}:{fresh_sig}".encode()).decode()
ok("  but one inside the window still works", I._user_from_state(fresh, db).id == user.id)

db.delete(victim); db.commit()

print("\n── The stored credential ──")
REFRESH = "1//0gFAKErefreshTOKENvalue"
I._upsert(db, user.id, "gmail", status="connected",
          credential=I._fernet().encrypt(REFRESH.encode()).decode(), metadata_json={})
row = db.query(Integration).filter(Integration.user_id == user.id,
                                   Integration.provider == "gmail").first()
ok("a row is stored", row is not None)
ok("  the refresh token is NOT in plaintext", REFRESH not in (row.credential or ""),
   (row.credential or "")[:40])
ok("  but decrypts back to the original",
   I._fernet().decrypt(row.credential.encode()).decode() == REFRESH)
ok("  and status now reports connected", I.status(user, db)["gmail"]["connected"] is True)

I._upsert(db, user.id, "gmail", status="connected", credential="x", metadata_json={})
ok("re-connecting updates in place rather than duplicating",
   db.query(Integration).filter(Integration.user_id == user.id,
                                Integration.provider == "gmail").count() == 1)

print("\n── Not a seeker feature for recruiters ──")
from api.access import require_seeker
rec = User(email="rec@integtest.example.com", name="R", account_type="recruiter",
           referral_code="integ3")
db.add(rec); db.commit(); db.refresh(rec)
m, d = raises(403, require_seeker, rec)
ok("a recruiter can't reach the integrations endpoints", m, d)

settings.GMAIL_CLIENT_ID, settings.GMAIL_CLIENT_SECRET, settings.INTEGRATION_ENCRYPTION_KEY = saved
for u in db.query(User).filter(User.email.like("%@integtest.example.com")).all():
    db.delete(u)
db.commit()

print(f"\n{'─'*46}\nPASS {P}    FAIL {F}")
for f in fails: print("  ✗", f)
db.close()
sys.exit(1 if F else 0)
