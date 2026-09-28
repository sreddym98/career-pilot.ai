# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Outbound email through Resend's HTTP API.

Best-effort by design: a failed notification must never fail the job that
triggered it, so this returns False instead of raising. With no RESEND_API_KEY
it logs and returns False, which keeps local dev and CI free of side effects.
"""
import requests
from api.settings import settings


def send(to: str, subject: str, text: str) -> bool:
    if not settings.RESEND_API_KEY:
        print(f"[mail] RESEND_API_KEY not set — not sending '{subject}' to {to}")
        return False
    try:
        r = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={"from": settings.MAIL_FROM, "to": [to], "subject": subject, "text": text},
            timeout=10)
        if r.status_code >= 400:
            print(f"[mail] Resend rejected '{subject}': {r.status_code} {r.text[:200]}")
            return False
        return True
    except requests.RequestException as e:
        print(f"[mail] Resend unreachable: {e}")
        return False
