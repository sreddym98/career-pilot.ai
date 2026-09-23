"""Gmail delivery uses encrypted refresh tokens and explicit user approval."""
import datetime as dt
import os
import sys
import types

os.environ.setdefault("DATABASE_URL", "sqlite:///./gmail_delivery_test.db")
os.environ.setdefault("ENV", "dev")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cryptography.fernet import Fernet
from fastapi import HTTPException
from api.db import SessionLocal, init_db
from api.models import Integration, User
from api.routers import integrations as gmail
from api.settings import settings

passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print(f"FAIL {name}")


class Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


init_db()
db = SessionLocal()
user = User(email="gmail-delivery@test.local", name="Gmail Test", referral_code="gmailtest")
db.add(user)
db.commit()
db.refresh(user)

original_post = gmail.requests.post
original_values = (settings.GMAIL_CLIENT_ID, settings.GMAIL_CLIENT_SECRET, settings.INTEGRATION_ENCRYPTION_KEY)
settings.GMAIL_CLIENT_ID = "client-id"
settings.GMAIL_CLIENT_SECRET = "client-secret"
settings.INTEGRATION_ENCRYPTION_KEY = Fernet.generate_key().decode()
fernet = Fernet(settings.INTEGRATION_ENCRYPTION_KEY.encode())
db.add(Integration(user_id=user.id, provider="gmail", status="connected",
                   credential=fernet.encrypt(b"refresh-token").decode(),
                   metadata_json={"account_email": user.email}, verified_at=dt.datetime.now(dt.timezone.utc)))
db.commit()

calls = []

def post(url, **kwargs):
    calls.append((url, kwargs))
    if url == gmail.GOOGLE_TOKEN_URL:
        return Response(200, {"access_token": "short-lived"})
    if url.endswith("/messages/send"):
        return Response(200, {"id": "gmail-message", "threadId": "gmail-thread"})
    return Response(500, {})

gmail.requests.post = post
try:
    result = gmail.gmail_send(gmail.GmailSendIn(
        to="recruiter@example.com", subject="Application", body="Hello",
        attachment_name="resume.docx", attachment_base64="cmVzdW1lIGJ5dGVz"), user, db)
    check("returns confirmed send result", result == {"sent": True, "message_id": "gmail-message", "thread_id": "gmail-thread"})
    check("refreshes token before sending", len(calls) == 2 and calls[0][0] == gmail.GOOGLE_TOKEN_URL)
    raw = calls[1][1]["json"]["raw"]
    check("encodes RFC email with attachment", b"resume.docx" in __import__("base64").urlsafe_b64decode(raw + "=="))

    db.query(Integration).filter(Integration.user_id == user.id, Integration.provider == "gmail").update({"status": "disconnected"})
    db.commit()
    try:
        gmail.gmail_send(gmail.GmailSendIn(to="recruiter@example.com", subject="Application", body="Hello"), user, db)
        check("disconnected account blocked", False)
    except HTTPException as error:
        check("disconnected account blocked", error.status_code == 409)
finally:
    gmail.requests.post = original_post
    settings.GMAIL_CLIENT_ID, settings.GMAIL_CLIENT_SECRET, settings.INTEGRATION_ENCRYPTION_KEY = original_values
    db.close()
    if os.path.exists("gmail_delivery_test.db"):
        os.remove("gmail_delivery_test.db")

print(f"PASS {passed} FAIL {failed}")
if failed:
    raise SystemExit(1)
