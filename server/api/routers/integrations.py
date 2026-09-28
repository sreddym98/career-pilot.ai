# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Google Gmail OAuth and Twilio Verify integration endpoints."""
import base64
import hashlib
import hmac
import secrets
import time
from html import escape
from urllib.parse import urlencode, urlparse

import requests
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth import current_user
from api.access import require_seeker
from api.db import get_db
from api.models import Integration, User
from api.ratelimit import per_user, client_ip, _enforce
from api.settings import settings

# These connect a mailbox and phone to Autopilot, which is a seeker feature.
# Gated per-endpoint, not on the router: /gmail/callback is Google's redirect
# and arrives with no session of ours attached.
router = APIRouter(prefix="/api/integrations", tags=["integrations"])
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
TWILIO_VERIFY_BASE = "https://verify.twilio.com/v2"


class PhoneStartIn(BaseModel):
    phone: str = Field(pattern=r"^\+[1-9]\d{7,14}$")


class PhoneConfirmIn(PhoneStartIn):
    code: str = Field(pattern=r"^\d{4,10}$")


def _gmail_missing() -> list[str]:
    """Names of the settings that stop the Google flow from being started.

    Empty means safe to send the user to Google. Anything else must NOT reach
    Google: an empty client_id or a localhost redirect_uri produces Google's
    "Access blocked: this app's request is invalid" page, which the user can
    do nothing about. Better a plain "not configured" from us."""
    missing = [k for k in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "INTEGRATION_ENCRYPTION_KEY")
               if not getattr(settings, k)]
    uri = (settings.GMAIL_REDIRECT_URI or "").strip()
    parsed = urlparse(uri)
    if not uri or parsed.scheme not in ("http", "https") or not parsed.netloc:
        missing.append("GMAIL_REDIRECT_URI")
    elif settings.ENV != "dev" and (parsed.scheme != "https" or parsed.hostname in ("localhost", "127.0.0.1")):
        # The default is a localhost URL; in production it means nobody set it.
        missing.append("GMAIL_REDIRECT_URI (must be the public https API callback URL)")
    return missing


def _configured_gmail():
    return not _gmail_missing()


def _configured_phone():
    return bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_VERIFY_SERVICE_SID)


def _fernet_key(raw: str) -> bytes:
    """A real Fernet key is used as-is. Anything else (a long random string from
    a password manager, say) is stretched into one with SHA-256, so the owner
    doesn't need Python just to mint a valid key. Same input, same key, so
    tokens stay decryptable across restarts."""
    try:
        Fernet(raw.encode())
        return raw.encode()
    except (TypeError, ValueError):
        return base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())


def _fernet():
    if not settings.INTEGRATION_ENCRYPTION_KEY:
        raise HTTPException(503, "Integration encryption is not configured")
    try:
        return Fernet(_fernet_key(settings.INTEGRATION_ENCRYPTION_KEY))
    except (TypeError, ValueError):
        raise HTTPException(503, "INTEGRATION_ENCRYPTION_KEY is invalid")


def _state_for(user_id: str):
    payload = f"{user_id}:{int(time.time())}:{secrets.token_urlsafe(18)}"
    signature = hmac.new(settings.INTEGRATION_ENCRYPTION_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{signature}".encode()).decode()


def _user_from_state(state: str, db: Session):
    try:
        raw = base64.urlsafe_b64decode(state.encode()).decode()
        user_id, issued, nonce, signature = raw.rsplit(":", 3)
        payload = f"{user_id}:{issued}:{nonce}"
        issued_at = int(issued)
    except Exception:
        raise HTTPException(400, "Invalid OAuth state")
    expected = hmac.new(settings.INTEGRATION_ENCRYPTION_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature.encode(), expected.encode()) or time.time() - issued_at > 600:
        raise HTTPException(400, "OAuth state expired. Start Gmail connection again.")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(400, "Account no longer exists")
    return user


def _upsert(db: Session, user_id: str, provider: str, **values):
    row = db.query(Integration).filter(Integration.user_id == user_id, Integration.provider == provider).first()
    if not row:
        row = Integration(user_id=user_id, provider=provider)
        db.add(row)
    for key, value in values.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


@router.get("/status")
def status(user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    rows = {row.provider: row for row in db.query(Integration).filter(Integration.user_id == user.id).all()}
    return {
        "gmail": {
            "configured": _configured_gmail(),
            "connected": rows.get("gmail") is not None and rows["gmail"].status == "connected",
        },
        "phone": {
            "configured": _configured_phone(),
            "verified": rows.get("phone") is not None and rows["phone"].status == "verified",
            "number": (rows.get("phone").metadata_json or {}).get("phone", "") if rows.get("phone") else "",
        },
    }


@router.get("/gmail/start", dependencies=[Depends(per_user("gmail_start", "RATE_GMAIL_START", "RATE_GMAIL_WINDOW_S"))])
def gmail_start(user: User = Depends(require_seeker)):
    missing = _gmail_missing()
    if missing:
        print(f"[gmail] not configured, refusing to start OAuth. Missing: {', '.join(missing)}")
        raise HTTPException(503, "Gmail connection isn't set up on this server yet. "
                                 "Nothing was sent to Google. The site owner needs to finish the Gmail configuration.")
    params = {
        "client_id": settings.GMAIL_CLIENT_ID,
        "redirect_uri": settings.GMAIL_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email https://www.googleapis.com/auth/gmail.send",
        "access_type": "offline",
        "prompt": "consent",
        "state": _state_for(user.id),
    }
    return {"authorization_url": f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"}


def _popup(message: str, connected: bool, status: int = 200) -> HTMLResponse:
    """The callback runs in the popup, so failures are shown there as a page,
    not as raw JSON. Only ever a fixed message, escaped."""
    origin = settings.FRONTEND_URL
    payload = "careerpilot:gmail-connected" if connected else "careerpilot:gmail-failed"
    return HTMLResponse(
        f"""<!doctype html><meta charset="utf-8"><title>Gmail</title>
<script>window.opener&&window.opener.postMessage({{type:{payload!r}}},{origin!r});{'window.close()' if connected else ''}</script>
<p style="font:16px system-ui;margin:32px">{escape(message)}</p>""", status_code=status)


@router.get("/gmail/callback", response_class=HTMLResponse)
def gmail_callback(code: str | None = Query(None), state: str | None = Query(None),
                   error: str | None = Query(None), db: Session = Depends(get_db)):
    if not _configured_gmail():
        return _popup("Gmail connection isn't set up on this server.", False, 503)
    if error or not code or not state:
        # Google sends ?error=access_denied when the user clicks Cancel/Deny.
        return _popup("Gmail was not connected. You can close this window and try again.", False, 400)
    try:
        user = _user_from_state(state, db)
    except HTTPException as e:
        return _popup(str(e.detail), False, e.status_code)
    try:
        response = requests.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.GMAIL_CLIENT_ID,
            "client_secret": settings.GMAIL_CLIENT_SECRET,
            "redirect_uri": settings.GMAIL_REDIRECT_URI,
            "grant_type": "authorization_code",
        }, timeout=15)
    except requests.RequestException:
        return _popup("Couldn't reach Google. Close this window and try again.", False, 502)
    if response.status_code != 200:
        print(f"[gmail] token exchange failed: {response.status_code} {response.text[:200]}")
        return _popup("Google did not accept the authorization. Close this window and try again.", False, 400)
    refresh = response.json().get("refresh_token")
    if not refresh:
        return _popup("Google did not return a refresh token. Remove CareerPilot from your Google account "
                      "permissions (myaccount.google.com/permissions) and connect again.", False, 400)
    _upsert(db, user.id, "gmail", status="connected", credential=_fernet().encrypt(refresh.encode()).decode(), metadata_json={})
    return _popup("Gmail connected. You may close this window.", True)


@router.post("/phone/start", dependencies=[Depends(per_user("phone_start", "RATE_PHONE_START", "RATE_PHONE_WINDOW_S"))])
def phone_start(body: PhoneStartIn, request: Request, user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    # Sign-up is open and unverified, so per-user limits alone let one person
    # mint accounts and pump SMS to premium numbers. Cap the source address too.
    _enforce([(f"phone_start_ip:{client_ip(request)}", settings.RATE_PHONE_START_PER_IP, settings.RATE_PHONE_WINDOW_S)])
    if not _configured_phone():
        raise HTTPException(503, "SMS verification is not configured. Add Twilio Verify credentials first.")
    response = requests.post(
        f"{TWILIO_VERIFY_BASE}/Services/{settings.TWILIO_VERIFY_SERVICE_SID}/Verifications",
        auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
        data={"To": body.phone, "Channel": "sms"}, timeout=15,
    )
    if response.status_code >= 400:
        raise HTTPException(400, "Twilio could not send a verification code")
    _upsert(db, user.id, "phone", status="pending", credential=None, metadata_json={"phone": body.phone})
    return {"sent": True}


@router.post("/phone/confirm")
def phone_confirm(body: PhoneConfirmIn, user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    if not _configured_phone():
        raise HTTPException(503, "SMS verification is not configured")
    response = requests.post(
        f"{TWILIO_VERIFY_BASE}/Services/{settings.TWILIO_VERIFY_SERVICE_SID}/VerificationCheck",
        auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
        data={"To": body.phone, "Code": body.code}, timeout=15,
    )
    if response.status_code >= 400 or response.json().get("status") != "approved":
        raise HTTPException(400, "That verification code was not accepted")
    _upsert(db, user.id, "phone", status="verified", credential=None, metadata_json={"phone": body.phone})
    return {"verified": True}
