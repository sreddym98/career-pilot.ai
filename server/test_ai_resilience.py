# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Ollama proxy failure handling. No network or local model required."""
import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./ai_test.db")
os.environ.setdefault("ENV", "dev")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import HTTPException
import requests
import api.routers.ai as AI

P = F = 0
fails = []


def ok(name, condition, detail=""):
    global P, F
    if condition:
        P += 1
    else:
        F += 1
        fails.append(f"{name} -> {detail}")


class Response:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {"response": '{"summary":"ok"}'}

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error

    def json(self):
        return self._body


calls = {"count": 0}
original_post = AI.requests.post


def mock_post(behavior):
    calls["count"] = 0

    def post(*args, **kwargs):
        calls["count"] += 1
        return behavior(calls["count"], args, kwargs)

    AI.requests.post = post


print("\nAI PROXY - Ollama failure handling\n")
try:
    mock_post(lambda count, args, kwargs: Response(500))
    try:
        AI._call("x", 100)
        ok("server error raises", False)
    except HTTPException as error:
        ok("server error -> 503 without a long retry", error.status_code == 503 and calls["count"] == 1, calls["count"])

    mock_post(lambda count, args, kwargs: Response(500))
    try:
        AI._call("x", 100)
        ok("persistent server error raises", False)
    except HTTPException as error:
        ok("persistent server error -> 503", error.status_code == 503, error.status_code)
        ok("  makes one request", calls["count"] == 1, calls["count"])

    mock_post(lambda count, args, kwargs: Response(400))
    try:
        AI._call("x", 100)
        ok("bad request raises", False)
    except HTTPException as error:
        ok("bad request -> 400 without retry", error.status_code == 400 and calls["count"] == 1, calls["count"])

    def disconnected(count, args, kwargs):
        raise requests.ConnectionError("Ollama offline")

    mock_post(disconnected)
    try:
        AI._call("x", 100)
        ok("connection failure raises", False)
    except HTTPException as error:
        ok("connection failure -> actionable 503", error.status_code == 503 and "Ollama" in error.detail, error.detail)

    mock_post(lambda count, args, kwargs: Response(body={"response": "```json\n{\"summary\":\"fenced\"}\n```"}))
    ok("strips markdown fences", AI._call("x", 100) == {"summary": "fenced"})

    mock_post(lambda count, args, kwargs: Response(body={"response": "not JSON"}))
    try:
        AI._call("x", 100, "Summary")
        ok("invalid model JSON raises", False)
    except HTTPException as error:
        ok("invalid model JSON -> 503", error.status_code == 503 and calls["count"] == 1, calls["count"])
    # ── /tailor takes a caller-supplied prompt, so it has to be metered ──
    # It previously spent no credits and cached nothing, and the resume builder
    # sends all of its work here: a free account could generate without limit.
    from api.db import SessionLocal, init_db
    from api.models import User, AICache
    from api import credits
    init_db()
    db = SessionLocal()
    u = db.query(User).filter(User.email == "tailor@aitest.example.com").first()
    if u: db.delete(u); db.commit()
    u = User(email="tailor@aitest.example.com", name="T", plan="free",
             referral_code="tailorck")
    db.add(u); db.commit(); db.refresh(u)

    # The AI cache is a real table and outlives the run. Without clearing the
    # keys this test uses, a second run is served from cache, never calls the
    # model, and never charges — so the metering assertions below would pass
    # against a stale entry rather than against the code.
    PROMPT, TOK = "write me a bullet", 200
    for p in (PROMPT, "a brand new prompt"):
        db.query(AICache).filter(AICache.cache_key == AI._key("tailor", AI.MODEL, p, TOK)).delete()
    db.commit()

    mock_post(lambda count, args, kwargs: Response(body={"response": '{"summary":"ok"}'}))
    before = credits.remaining(db, u)
    r1 = AI.tailor(AI.PromptReq(prompt=PROMPT, max_tokens=TOK), u, db)
    ok("tailor returns the model's answer", r1["data"] == {"summary": "ok"})
    ok("  and charges a generation", credits.remaining(db, u) == before - 1,
       f"{before} -> {credits.remaining(db, u)}")

    calls["count"] = 0
    r2 = AI.tailor(AI.PromptReq(prompt=PROMPT, max_tokens=TOK), u, db)
    ok("  identical prompt is served from cache", r2.get("cached") is True)
    ok("    without calling the model", calls["count"] == 0, calls["count"])
    ok("    and without charging again", credits.remaining(db, u) == before - 1)

    u.credits_used = 10_000; db.commit()
    try:
        AI.tailor(AI.PromptReq(prompt="a brand new prompt", max_tokens=TOK), u, db)
        ok("out of credits is refused", False)
    except HTTPException as error:
        ok("out of credits is refused", error.status_code == 429, error.status_code)

    db.delete(u); db.commit(); db.close()
finally:
    AI.requests.post = original_post

print("\n" + "=" * 48)
print(f"PASS {P}    FAIL {F}")
if F:
    print("\nFAILURES")
    for failure in fails:
        print("  x " + failure)
    raise SystemExit(1)
print("ALL GREEN")
