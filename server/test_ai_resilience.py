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
