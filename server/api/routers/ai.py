# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""AI proxy using Ollama (local, free, no API key needed).

Ollama runs locally on http://localhost:11434 and provides fast inference
without any cloud dependencies, API keys, or cost.
"""
import hashlib, json, requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from api.db import get_db
from api.auth import current_user
from api.models import User, AICache, Position
from api.settings import settings
from api import credits

class _Transient(Exception):
    """Retryable condition that isn't one of ollama's typed errors."""


router = APIRouter(prefix="/api/ai", tags=["ai"])
OLLAMA_URL = "http://localhost:11434"
MODEL = "neural-chat"  # Faster and more efficient than mistral


def _key(*parts) -> str:
    return hashlib.sha256("||".join(map(str, parts)).encode()).hexdigest()


def _cached(db, key):
    row = db.query(AICache).get(key)
    if row:
        row.hits += 1
        db.commit()
        return row.result
    return None


def _store(db, key, result):
    db.merge(AICache(cache_key=key, result=result))
    db.commit()


def _call(prompt: str, max_tokens: int = 1400, label: str = "") -> dict:
    """Call Ollama locally and fail quickly so the UI can use its fallback."""
    import time
    import re
    last = None
    for attempt in range(1, 2):
        try:
            # Call Ollama's generate endpoint
            response = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "num_predict": min(max_tokens, 420),
                        "temperature": 0.3,
                        "top_p": 0.9,
                    },
                },
                 timeout=20,
            )
            response.raise_for_status()
            
            data = response.json()
            text = data.get("response", "").strip()
            
            if not text:
                raise _Transient("empty response from model")
            
            # Try to extract JSON from the response
            # First, remove code block markers if present
            text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            
            # Try to find JSON object if it's embedded in text
            if not text.startswith('{'):
                # Look for JSON object in the text
                match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text)
                if match:
                    text = match.group(0)
            
            # Attempt to parse as JSON
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                # If JSON parsing fails, raise a transient error to retry
                raise _Transient("response was not valid JSON")

        except (_Transient, requests.ConnectionError, requests.Timeout) as e:
            last = e
            if attempt == 1:
                break
            time.sleep(1.0 * (2 ** (attempt - 1)))  # Increased backoff
        except requests.HTTPError as e:
            if e.response.status_code >= 500:
                last = e
                if attempt == 1:
                    break
                time.sleep(1.0 * (2 ** (attempt - 1)))
            else:
                raise HTTPException(400, f"Request rejected: {str(e)[:160]}")

    # All attempts failed
    if isinstance(last, requests.ConnectionError):
        raise HTTPException(503, 
            "Ollama service is not running. Start with: ollama serve")
    elif isinstance(last, requests.Timeout):
        raise HTTPException(503, 
            "Ollama is taking too long to respond. Try again in a moment.")
    
    kind = type(last).__name__ if last else "unknown"
    raise HTTPException(503, f"AI service temporarily unavailable ({kind}). "
                             f"Retry in a moment — completed sections are kept.")


class TailorReq(BaseModel):
    jd: str
    title: str = ""
    specialization: str = ""
    emphasis: str = "balanced"
    depth: str = "exactly 10 to 12"


class PromptReq(BaseModel):
    prompt: str
    max_tokens: int = 1400
    label: str = ""


@router.post("/tailor")
def tailor(req: PromptReq, user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    """Single AI call with any prompt. Used by the resume builder frontend."""
    result = _call(req.prompt, req.max_tokens, req.label)
    return {"data": result}


@router.post("/resume")
def build_resume(req: TailorReq, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    """One call per role. Each role gets the full token budget, which is
    what makes 10-15 detailed bullets possible without truncating."""
    if user.plan == "free":
        raise HTTPException(402, "Resume tailoring is a Pro feature")

    positions = db.query(Position).filter(Position.user_id == user.id).all()
    if not positions:
        raise HTTPException(400, "Add at least one role to your profile first")

    need = 1 + len(positions)
    if credits.remaining(db, user) < need:
        raise HTTPException(429,
            f"This needs {need} generations; you have {credits.remaining(db, user)} left this month. "
            f"Refer a friend for +100/month.")

    skills = [s.skill for s in user.skills] if hasattr(user, "skills") else []
    jd = req.jd[:1500]
    ctx = f"TARGET\nTitle: {req.title}\nSpecialization: {req.specialization}\nEmphasis: {req.emphasis}\n" \
          + (f"JOB DESCRIPTION:\n{jd}" if jd else "No JD — write for the specialization generally.")

    total_months = sum(p.months for p in positions)
    y, mo = divmod(total_months, 12)
    total_label = (f"{y} yrs " if y else "") + (f"{mo} mos" if mo else "")

    # ── header ──
    hk = _key("header", user.id, req.title, req.specialization, req.emphasis, jd)
    header = _cached(db, hk)
    if header is None:
        header = _call(f"""Write the header of a senior technical resume. Return ONLY minified JSON.

CANDIDATE: {user.name} — {total_label} total
Roles: {'; '.join(f'{p.role} at {p.company}' for p in positions)}
Skills: {', '.join(skills)}

{ctx}

SCHEMA {{"summary":"","skill_groups":[{{"label":"","items":[""]}}]}}

RULES
- summary: 4-5 sentences, max 600 chars. Concrete. Name real tools and domains.
  No "results-driven professional", no "proven track record", no filler adjectives.
- skill_groups: 5-7 groups, 6-10 items each, grouped by function.
- Only use skills from the list. Never invent one.""", 1000)
        _store(db, hk, header)
        credits.spend(db, user)

    # ── one call per role ──
    roles = []
    for p in positions:
        rk = _key("role", p.id, req.title, req.specialization, req.depth, jd,
                  json.dumps(p.bullets, sort_keys=True))
        got = _cached(db, rk)
        if got is None:
            got = _call(f"""Write ONE role's bullets for a senior technical resume. Return ONLY minified JSON.

ROLE
Company: {p.company}
Title: {p.role}
Dates: {p.started_on:%b %Y} – {p.finished_on:%b %Y if p.finished_on else 'Present'}
Location: {p.location or ''}

SOURCE MATERIAL — expand on these, never go beyond them
{chr(10).join('- ' + b for b in (p.bullets or []))}

SKILLS AVAILABLE (use only ones plausibly used in this role)
{', '.join(skills)}

{ctx}

SCHEMA {{"bullets":[""]}}

RULES
- Produce {req.depth} bullets. Fewer is a failure.
- Each 120-200 characters. Detailed and specific, not one-liners.
- Every bullet traces back to the source material. Expand one source line into
  2-3 bullets by naming concrete tools, techniques, and surfaces.
- NEVER invent metrics, percentages, projects, or employers.
- Start with a strong past-tense verb; vary them.
- Lead with what's most relevant to the target.""", 1400, p.company)
            _store(db, rk, got)
            credits.spend(db, user)   # only after a successful call
        roles.append({
            "company": p.company, "role": p.role,
            "dates": f"{p.started_on:%b %Y} – " + (f"{p.finished_on:%b %Y}" if p.finished_on else "Present"),
            "duration": p.duration_label, "location": p.location,
            "bullets": got.get("bullets", []),
        })

    return {"summary": header.get("summary", ""),
            "skill_groups": header.get("skill_groups", []),
            "experience": roles,
            "total_experience": total_label,
            "credits_remaining": credits.remaining(db, user)}


class CoverReq(BaseModel):
    fingerprint: str
    tone: str = "direct"


@router.post("/cover-letter")
def cover_letter(req: CoverReq, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    from api.models import Job
    if user.plan == "free":
        raise HTTPException(402, "Cover letters are a Pro feature")
    if credits.remaining(db, user) < 1:
        raise HTTPException(429, "No generations left this month")
    job = db.query(Job).get(req.fingerprint)
    if not job:
        raise HTTPException(404, "Job not found")

    k = _key("cover", user.id, job.fingerprint, req.tone)
    got = _cached(db, k)
    if got is None:
        got = _call(f"""Write a cover letter. Return ONLY minified JSON.

CANDIDATE: {user.name} — {user.headline}
ROLE: {job.title} at {job.company} ({job.location})
JD: {(job.description or '')[:1500]}

SCHEMA {{"cover_letter":"","fields":{{"why_interested":"","salary_expectation":"","availability":"","relocation":"","visa_answer":""}}}}

RULES
- 3 short paragraphs. Specific to this role. No "I am writing to express interest".
- salary_expectation: if the posting states a range, say it works; otherwise
  "open to your offer". NEVER invent a number the candidate didn't give.
- visa_answer: state the candidate's status plainly, no hedging.""", 1200, "cover letter")
        _store(db, k, got)
        credits.spend(db, user)
    return got


@router.get("/credits")
def my_credits(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"used": user.credits_used or 0,
            "allowance": credits.allowance(db, user),
            "remaining": credits.remaining(db, user),
            "active_referrals": credits.active_referrals(db, user.id),
            "plan": user.plan}
