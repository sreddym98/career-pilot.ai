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

# ── OpenAI-compatible gateway path (_call_openai) ──
class GwResponse:
    def __init__(self, status=200, body=None, text=""):
        self.status_code = status
        self._body = body
        self.text = text or "upstream-secret-detail-key-sk-123"
    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body

def _gw_body(content):
    return {"choices": [{"message": {"content": content}}]}

_saved = (AI.settings.AI_API_KEY, AI.settings.AI_BASE_URL)
_saved_post = AI.requests.post
AI.settings.AI_API_KEY = "test-key"
AI.settings.AI_BASE_URL = "https://gateway.example.test/v1"
try:
    seen = {}
    def gw_ok(url, **kw):
        seen["url"] = url; seen["auth"] = kw["headers"]["Authorization"]
        return GwResponse(200, _gw_body('{"summary": "gw ok"}'))
    AI.requests.post = gw_ok
    out = AI._call_openai("p", 100, 5, False)
    ok("gateway: success parses the JSON answer", out == {"summary": "gw ok"}, out)
    ok("gateway: hits <base>/chat/completions with the key",
       seen["url"] == "https://gateway.example.test/v1/chat/completions" and seen["auth"] == "Bearer test-key", seen)

    AI.requests.post = lambda *a, **k: GwResponse(200, _gw_body('```json\n{"summary": "fenced"}\n```'))
    ok("gateway: fenced JSON is unwrapped", AI._call_openai("p", 100, 5, False) == {"summary": "fenced"})

    def expect_503(name, fn, forbidden=()):
        AI.requests.post = fn
        try:
            AI._call_openai("p", 100, 5, False)
            ok(name, False, "no exception")
        except HTTPException as e:
            leaked = [f for f in forbidden if f in str(e.detail)]
            ok(name, e.status_code == 503 and not leaked, (e.status_code, e.detail))

    expect_503("gateway: 401 -> 503 without leaking detail",
               lambda *a, **k: GwResponse(401), forbidden=("sk-123", "upstream-secret", "401"))
    expect_503("gateway: 429 -> 503", lambda *a, **k: GwResponse(429))
    expect_503("gateway: 500 -> 503", lambda *a, **k: GwResponse(500))
    def _timeout(*a, **k): raise requests.Timeout("slow")
    expect_503("gateway: timeout -> 503", _timeout)
    def _conn(*a, **k): raise requests.ConnectionError("refused")
    expect_503("gateway: connection error -> 503", _conn)
    expect_503("gateway: unreadable answer -> 503",
               lambda *a, **k: GwResponse(200, {"choices": []}))

    AI.settings.AI_API_KEY = ""
    try:
        AI._call_openai("p", 100, 5, False)
        ok("gateway: unconfigured -> 503", False)
    except HTTPException as e:
        ok("gateway: unconfigured -> 503", e.status_code == 503, e.status_code)

    print("\n── gateway ladder: JSON mode, then plain, then the main model ──")
    AI.settings.AI_API_KEY, AI.settings.AI_BASE_URL = "k", "https://gw.example/v1"
    AI.settings.AI_MODEL, AI.settings.AI_FAST_MODEL = "main-m", "fast-m"

    class _R:
        def __init__(self, status, body):
            self.status_code, self._b = status, body
            self.text = str(body)
        def json(self): return self._b

    GOOD = {"choices": [{"message": {"content": '{"ok": true}'}}]}
    def script(*steps):
        seen = []
        def post(url, headers=None, json=None, timeout=None):
            seen.append((json["model"], "response_format" in json))
            return steps[min(len(seen) - 1, len(steps) - 1)]
        AI.requests.post = post
        return seen

    seen = script(_R(500, {"error": "response_format not supported"}), _R(200, GOOD))
    r = AI._call("x", 100, "t", fast=True)
    ok("500 in JSON mode then works without it", r == {"ok": True} and seen == [("fast-m", True), ("fast-m", False)], seen)

    seen = script(_R(404, "no such model"), _R(404, "no such model"), _R(200, GOOD))
    r = AI._call("x", 100, "t", fast=True)
    ok("refused fast model falls back to the main model",
       r == {"ok": True} and seen[-1] == ("main-m", False), seen)

    seen = script(_R(401, "bad key"))
    try:
        AI._call("x", 100, "t", fast=True); ok("bad key raises", False)
    except HTTPException as e:
        ok("bad key is not retried", e.status_code == 503 and len(seen) == 1, (e.status_code, seen))
    ok("the gateway's own status is kept for the operator", AI.LAST_GATEWAY_ERROR["status"] == 401)

    seen = script(_R(503, "overloaded"))
    try:
        AI._call("x", 100, "t", fast=True); ok("all-503 raises", False)
    except HTTPException as e:
        ok("persistent 503 is reported as busy", e.status_code == 503 and "busy" in e.detail.lower(), e.detail)

    seen = script(_R(200, GOOD))
    AI._call("x", 100, "t", fast=False)
    ok("main-model call uses the main model once", seen == [("main-m", True)], seen)
finally:
    AI.settings.AI_API_KEY, AI.settings.AI_BASE_URL = _saved
    AI.requests.post = _saved_post

print("\n" + "=" * 48)
print(f"PASS {P}    FAIL {F}")
if F:
    print("\nFAILURES")
    for failure in fails:
        print("  x " + failure)
    raise SystemExit(1)
print("ALL GREEN")
