# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Upstream failure handling in the AI proxy. No network, no credits spent."""
import os, sys, types, json
os.environ.setdefault("DATABASE_URL", "sqlite:///./ai_test.db")
os.environ.setdefault("ENV", "dev")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

P = F = 0; fails = []
def ok(n, c, x=""):
    global P, F
    if c: P += 1
    else: F += 1; fails.append(f"{n}  →  {x}")

import anthropic, httpx
from fastapi import HTTPException
import api.routers.ai as AI

# anthropic's exceptions need a real httpx.Response to construct
def _resp(code):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return httpx.Response(code, request=req)

def E(cls, code, msg="err"):
    return cls(msg, response=_resp(code), body=None)

calls = {"n": 0}

def mock_client(behaviour):
    calls["n"] = 0
    class M:
        class messages:
            @staticmethod
            def create(**kw):
                calls["n"] += 1
                return behaviour(calls["n"])
    AI.client = M()

def good(text):
    return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=text)])

print("\n╔═══ AI PROXY — upstream failures ═══╗\n")

# transient then success
def flaky(n):
    if n < 3: raise E(anthropic.InternalServerError, 500, "overloaded")
    return good('{"summary":"ok"}')
mock_client(flaky)
try:
    r = AI._call("x", 100, "test")
    ok("recovers after 2 transient failures", r == {"summary": "ok"})
    ok("  took 3 attempts", calls["n"] == 3, f"{calls['n']}")
except Exception as e:
    ok("recovers after 2 transient failures", False, f"{type(e).__name__}: {e}")

# persistent 5xx
mock_client(lambda n: (_ for _ in ()).throw(E(anthropic.InternalServerError, 500, "down")))
try:
    AI._call("x", 100, "test"); ok("persistent 5xx raises", False)
except HTTPException as e:
    ok("persistent 5xx → 503", e.status_code == 503, str(e.status_code))
    ok("  message is actionable", "temporarily unavailable" in e.detail and "kept" in e.detail, e.detail[:80])
    ok("  retried 3x", calls["n"] == 3, f"{calls['n']}")

# rate limit
mock_client(lambda n: (_ for _ in ()).throw(E(anthropic.RateLimitError, 429, "slow down")))
try:
    AI._call("x", 100); ok("rate limit raises", False)
except HTTPException as e:
    ok("rate limit → 429", e.status_code == 429, str(e.status_code))
    ok("  says sections are kept", "kept" in e.detail)

# auth — must NOT retry
mock_client(lambda n: (_ for _ in ()).throw(E(anthropic.AuthenticationError, 401, "bad key")))
try:
    AI._call("x", 100); ok("auth error raises", False)
except HTTPException as e:
    ok("auth → 500, no retry", e.status_code == 500 and calls["n"] == 1, f"{e.status_code}, {calls['n']} calls")
    ok("  names the env var", "ANTHROPIC_API_KEY" in e.detail)

# bad request — must NOT retry
mock_client(lambda n: (_ for _ in ()).throw(E(anthropic.BadRequestError, 400, "too long")))
try:
    AI._call("x", 100); ok("bad request raises", False)
except HTTPException as e:
    ok("400 → no retry", e.status_code == 400 and calls["n"] == 1, f"{calls['n']} calls")

# malformed JSON — surfaced clearly, not as a parse error
mock_client(lambda n: good("this is not json at all"))
try:
    AI._call("x", 100, "Mastercard"); ok("bad JSON raises", False)
except HTTPException as e:
    ok("malformed JSON → 502", e.status_code == 502)
    ok("  names the failing section", "Mastercard" in e.detail, e.detail[:70])
    ok("  suggests a fix", "lower detail" in e.detail or "shorter" in e.detail)

# markdown fences tolerated
mock_client(lambda n: good('```json\n{"summary":"fenced"}\n```'))
ok("strips markdown fences", AI._call("x", 100) == {"summary": "fenced"})

print("\n" + "=" * 48)
print(f"PASS {P}    FAIL {F}")
if F: print("\nFAILURES"); [print("  ✗ " + f) for f in fails]
else: print("✓ ALL GREEN")
os.path.exists("ai_test.db") and os.remove("ai_test.db")
