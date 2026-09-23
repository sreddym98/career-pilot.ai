# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Google Gmail OAuth and Twilio Verify integration endpoints."""
import base64
import hashlib
import hmac
import secrets
import time
from email.message import EmailMessage
from mimetypes import guess_type
from urllib.parse import urlencode

import requests
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from api.auth import current_user
from api.access import require_seeker
from api.db import get_db
from api.models import Integration, User
from api.settings import settings

# These connect a mailbox and phone to Autopilot, which is a seeker feature.
# Gated per-endpoint, not on the router: /gmail/callback is Google's redirect
# and arrives with no session of ours attached.
router = APIRouter(prefix="/api/integrations", tags=["integrations"])
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API_URL = "https://gmail.googleapis.com/gmail/v1/users/me"
TWILIO_VERIFY_BASE = "https://verify.twilio.com/v2"


class PhoneStartIn(BaseModel):
    phone: str = Field(pattern=r"^\+[1-9]\d{7,14}$")


class PhoneConfirmIn(PhoneStartIn):
    code: str = Field(pattern=r"^\d{4,10}$")


class GmailSendIn(BaseModel):
    to: EmailStr
    subject: str = Field(min_length=1, max_length=250)
    body: str = Field(min_length=1, max_length=20000)
    attachment_name: str = Field(default="", max_length=180)
    attachment_base64: str = Field(default="", max_length=8_000_000)


def _configured_gmail():
    return bool(settings.GMAIL_CLIENT_ID and settings.GMAIL_CLIENT_SECRET and settings.INTEGRATION_ENCRYPTION_KEY)


def _configured_phone():
    return bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_VERIFY_SERVICE_SID)


def _fernet():
    if not settings.INTEGRATION_ENCRYPTION_KEY:
        raise HTTPException(503, "Integration encryption is not configured")
    try:
        return Fernet(settings.INTEGRATION_ENCRYPTION_KEY.encode())
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
    except Exception:
        raise HTTPException(400, "Invalid OAuth state")
    expected = hmac.new(settings.INTEGRATION_ENCRYPTION_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected) or time.time() - int(issued) > 600:
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


def _gmail_access_token(row: Integration, db: Session):
    """Exchange the encrypted long-lived refresh token for a short-lived token."""
    if not row.credential:
        raise HTTPException(409, "Reconnect Gmail to read your inbox")
    try:
        refresh_token = _fernet().decrypt(row.credential.encode()).decode()
    except InvalidToken:
        raise HTTPException(409, "Gmail credentials can no longer be read. Reconnect Gmail.")
    response = requests.post(GOOGLE_TOKEN_URL, data={
        "client_id": settings.GMAIL_CLIENT_ID,
        "client_secret": settings.GMAIL_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }, timeout=15)
    if response.status_code != 200:
        row.status = "disconnected"
        db.commit()
        raise HTTPException(409, "Gmail connection expired or was revoked. Reconnect Gmail.")
    token = response.json().get("access_token")
    if not token:
        raise HTTPException(502, "Google did not return a mailbox access token")
    return token


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


@router.get("/gmail/start")
def gmail_start(user: User = Depends(require_seeker)):
    if not _configured_gmail():
        raise HTTPException(503, "Gmail OAuth is not configured. Add GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, and INTEGRATION_ENCRYPTION_KEY.")
    params = {
        "client_id": settings.GMAIL_CLIENT_ID,
        "redirect_uri": settings.GMAIL_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly",
        "access_type": "offline",
        "prompt": "consent",
        "state": _state_for(user.id),
    }
    return {"authorization_url": f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"}


@router.get("/gmail/callback", response_class=HTMLResponse)
def gmail_callback(code: str = Query(...), state: str = Query(...), db: Session = Depends(get_db)):
    if not _configured_gmail():
        raise HTTPException(503, "Gmail OAuth is not configured")
    user = _user_from_state(state, db)
    response = requests.post(GOOGLE_TOKEN_URL, data={
        "code": code,
        "client_id": settings.GMAIL_CLIENT_ID,
        "client_secret": settings.GMAIL_CLIENT_SECRET,
        "redirect_uri": settings.GMAIL_REDIRECT_URI,
        "grant_type": "authorization_code",
    }, timeout=15)
    if response.status_code != 200:
        raise HTTPException(400, "Google did not accept the authorization code")
    token = response.json()
    refresh = token.get("refresh_token")
    if not refresh:
        raise HTTPException(400, "Google did not return a refresh token. Remove CareerPilot from Google account permissions and connect again.")
    access_token = token.get("access_token", "")
    account_email = ""
    if access_token:
        profile = requests.get(f"{GMAIL_API_URL}/profile", headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
        if profile.status_code == 200:
            account_email = profile.json().get("emailAddress", "")
    _upsert(db, user.id, "gmail", status="connected", credential=_fernet().encrypt(refresh.encode()).decode(), metadata_json={"account_email": account_email})
    return HTMLResponse(f"""<!doctype html><title>Gmail connected</title><script>window.opener&&window.opener.postMessage({{type:'careerpilot:gmail-connected'}},{settings.FRONTEND_URL!r});window.close()</script><p>Gmail connected. You may close this window.</p>""")


@router.get("/gmail/messages")
def gmail_messages(limit: int = Query(30, ge=1, le=100), user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    """Return recent inbox metadata only; message bodies never leave Gmail."""
    if not _configured_gmail():
        raise HTTPException(503, "Gmail OAuth is not configured")
    row = db.query(Integration).filter(Integration.user_id == user.id, Integration.provider == "gmail", Integration.status == "connected").first()
    if not row:
        raise HTTPException(409, "Connect Gmail to see application replies")
    headers = {"Authorization": f"Bearer {_gmail_access_token(row, db)}"}
    listing = requests.get(f"{GMAIL_API_URL}/messages", headers=headers,
                           params={"labelIds": "INBOX", "q": "newer_than:90d", "maxResults": limit}, timeout=20)
    if listing.status_code != 200:
        raise HTTPException(502, "Google could not load your inbox")
    messages = []
    for item in listing.json().get("messages", []):
        detail = requests.get(f"{GMAIL_API_URL}/messages/{item['id']}", headers=headers,
                              params=[("format", "metadata"), ("metadataHeaders", "From"), ("metadataHeaders", "Subject"), ("metadataHeaders", "Date")], timeout=15)
        if detail.status_code != 200:
            continue
        data = detail.json()
        values = {header["name"].lower(): header.get("value", "") for header in data.get("payload", {}).get("headers", [])}
        messages.append({
            "id": data["id"], "thread_id": data.get("threadId", ""), "from": values.get("from", ""),
            "subject": values.get("subject", "(no subject)"), "date": values.get("date", ""),
            "snippet": data.get("snippet", ""), "unread": "UNREAD" in data.get("labelIds", []),
        })
    return {"account_email": (row.metadata_json or {}).get("account_email", ""), "messages": messages}


@router.post("/gmail/send")
def gmail_send(body: GmailSendIn, user: User = Depends(require_seeker), db: Session = Depends(get_db)):
    """Send only an explicitly approved message through the user's Gmail account."""
    if not _configured_gmail():
        raise HTTPException(503, "Gmail OAuth is not configured")
    row = db.query(Integration).filter(Integration.user_id == user.id, Integration.provider == "gmail", Integration.status == "connected").first()
    if not row:
        raise HTTPException(409, "Connect Gmail before sending an application email")
    message = EmailMessage()
    message["To"] = str(body.to)
    message["Subject"] = body.subject.replace("\r", " ").replace("\n", " ").strip()
    message.set_content(body.body)
    if body.attachment_base64:
        try:
            attachment = base64.b64decode(body.attachment_base64, validate=True)
        except ValueError:
            raise HTTPException(400, "Resume attachment could not be read")
        if len(attachment) > 5_000_000:
            raise HTTPException(400, "Resume attachment must be under 5 MB")
        filename = body.attachment_name.replace("/", "_").replace("\\", "_") or "resume.docx"
        mime, _ = guess_type(filename)
        major, minor = (mime or "application/octet-stream").split("/", 1)
        message.add_attachment(attachment, maintype=major, subtype=minor, filename=filename)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode().rstrip("=")
    response = requests.post(f"{GMAIL_API_URL}/messages/send", headers={"Authorization": f"Bearer {_gmail_access_token(row, db)}"}, json={"raw": raw}, timeout=20)
    if response.status_code >= 400:
        raise HTTPException(502, "Gmail could not send this message")
    sent = response.json()
    return {"sent": True, "message_id": sent.get("id", ""), "thread_id": sent.get("threadId", "")}


@router.post("/phone/start")
def phone_start(body: PhoneStartIn, user: User = Depends(require_seeker), db: Session = Depends(get_db)):
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
