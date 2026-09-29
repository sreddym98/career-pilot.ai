# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Tailored resume for one job, built ONLY from the user's own profile.

Structure (stored on Application.tailored_resume["resume"]):

    {"summary": str, "skills": [str],
     "roles": [{"id", "company", "role", "dates", "location", "bullets": [str]}],
     "ai": bool}

Employers, titles, dates and locations are always copied from the Position
rows, never from model output: the model only returns bullets keyed by a
position id we gave it. check_ai() then rejects any draft that introduces a
number, a known skill/tool, or a placeholder the profile doesn't contain.
"""
import datetime as dt
import io
import re

from ingest.skills import _COMPILED

MAX_BULLETS = 8
_PLACEHOLDER = re.compile(r"\[[^\]\n]{2,40}\]|\{\{|\}\}|lorem ipsum|\bTBD\b|<[A-Za-z ]{3,30}>|X+%|\bN\+? years", re.I)
_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def _dates(p) -> str:
    return f"{p.started_on:%b %Y} – " + (f"{p.finished_on:%b %Y}" if p.finished_on else "Present")


def _ordered(positions):
    return sorted(positions, key=lambda p: p.started_on, reverse=True)


def skills_in(text: str) -> set[str]:
    """Every vocabulary skill literally mentioned in `text` (no cap)."""
    return {name.lower() for name, rx in _COMPILED if rx.search(text or "")}


def source_text(user, positions, skills) -> str:
    from api.ats import years_of_experience
    ps = _ordered(positions)
    bits = [user.name or "", user.headline or "", user.summary or "", user.location or ""]
    for p in ps:
        bits += [p.company, p.role, p.location or "", _dates(p), *(p.bullets or [])]
    bits.append(", ".join(skills))
    if ps:
        y = years_of_experience(ps)
        bits.append(f"{y} years {y}+ years")
    return "\n".join(bits)


def _job_skills(job) -> list[str]:
    js = [s.lower() for s in (job.required_skills or [])]
    for s in skills_in(f"{job.title}\n{job.description or ''}"):
        if s not in js:
            js.append(s)
    return js


def _relevance(text: str, job_sk: list[str]) -> int:
    t = text.lower()
    return sum(1 for s in job_sk if s and s in t)


def base_resume(user, positions, skills, job) -> dict:
    """No AI: the profile as-is, with each role's bullets and the skills list
    ordered by relevance to this job. Always available and always free."""
    job_sk = _job_skills(job)
    roles = []
    for p in _ordered(positions):
        bl = [b for b in (p.bullets or []) if isinstance(b, str) and b.strip()]
        bl = sorted(bl, key=lambda b: -_relevance(b, job_sk))       # stable: ties keep the user's order
        roles.append({"id": p.id, "company": p.company, "role": p.role, "dates": _dates(p),
                      "location": p.location or "", "bullets": bl[:MAX_BULLETS]})
    wanted = {s.lower() for s in job_sk}
    sk = sorted(skills, key=lambda s: 0 if s.lower() in wanted else 1)
    return {"summary": (user.summary or user.headline or "").strip()[:900], "skills": sk,
            "roles": roles, "ai": False}


def prompt(user, positions, skills, job) -> str:
    ps = _ordered(positions)
    lines = []
    for i, p in enumerate(ps, 1):
        lines.append(f"P{i}: {p.role} at {p.company} ({_dates(p)})")
        lines += [f"  - {b[:240]}" for b in (p.bullets or [])[:10]]
    return f"""Tailor a resume and cover letter to ONE job. Return ONLY minified JSON.

CANDIDATE: {user.name or ''}
Headline: {user.headline or ''}
Summary: {(user.summary or '')[:600]}
Skills: {', '.join(skills[:60])}
Roles:
{chr(10).join(lines)}

JOB: {job.title} at {job.company} ({job.location or 'location not stated'})
Job skills: {', '.join((job.required_skills or [])[:25])}
JD: {(job.description or '')[:1500]}

SCHEMA {{"summary":"","roles":[{{"id":"P1","bullets":[""]}}],"skills":[""],"cover_letter":""}}

RULES
- Use ONLY facts in the CANDIDATE block. NEVER invent employers, titles, dates, tools, skills, metrics or numbers.
- summary: 3-4 sentences aimed at this job, no filler adjectives.
- roles: for each P id, rewrite and reorder THAT role's own bullets so the most relevant to this job come first; at most {MAX_BULLETS}; each traces to one of that role's bullets.
- skills: the candidate's skills, most relevant to this job first. Only from the Skills list.
- cover_letter: 3 short paragraphs for this job. No "I am writing to express interest". No salary."""


def check_ai(got, user, positions, skills, job):
    """(resume, cover_letter) or (None, reason). Untrusted model output."""
    if not isinstance(got, dict):
        return None, "not an object"
    ps = _ordered(positions)
    by_key = {f"P{i}": p for i, p in enumerate(ps, 1)}
    src = source_text(user, positions, skills)
    src_norm = re.sub(r"[\s,]", "", src.lower())
    allowed_sk = skills_in(src) | {s.lower() for s in skills}

    summary = got.get("summary") if isinstance(got.get("summary"), str) else ""
    letter = got.get("cover_letter") if isinstance(got.get("cover_letter"), str) else ""
    roles_in = got.get("roles") if isinstance(got.get("roles"), list) else []
    sk_in = got.get("skills") if isinstance(got.get("skills"), list) else []

    bullets_by_id = {}
    for r in roles_in:
        if not isinstance(r, dict):
            return None, "bad role"
        rid = str(r.get("id") or "").strip()
        if rid not in by_key:
            return None, f"unknown role id {rid!r}"            # an employer we never gave it
        bl = [b.strip()[:320] for b in (r.get("bullets") or []) if isinstance(b, str) and b.strip()]
        if bl:
            bullets_by_id[rid] = bl[:MAX_BULLETS]
    if not summary.strip() or not bullets_by_id:
        return None, "empty draft"

    out_sk = []
    for s in sk_in:
        if not isinstance(s, str) or not s.strip():
            continue
        if s.strip().lower() not in {x.lower() for x in skills}:
            return None, f"invented skill {s!r}"
        out_sk.append(next(x for x in skills if x.lower() == s.strip().lower()))

    resume_text = " ".join([summary, *[b for bl in bullets_by_id.values() for b in bl]])
    job_bits = f"{job.title} {job.company} {job.location or ''}"
    for blob, extra in ((resume_text, ""), (letter, job_bits)):
        if _PLACEHOLDER.search(blob):
            return None, "placeholder"
        ok_norm = src_norm + re.sub(r"[\s,]", "", extra.lower())
        for n in _NUM.findall(blob):
            if re.sub(r"[\s,]", "", n) not in ok_norm:
                return None, f"invented number {n!r}"
    new_sk = skills_in(resume_text + "\n" + letter) - allowed_sk
    # A skill that is only the employer's/job title's name (e.g. "Salesforce"
    # the company) is fine in the cover letter; anything else is invented.
    new_sk -= skills_in(job_bits)
    if new_sk:
        return None, f"invented tools {sorted(new_sk)}"

    roles = []
    for key, p in by_key.items():
        roles.append({"id": p.id, "company": p.company, "role": p.role, "dates": _dates(p),
                      "location": p.location or "",
                      "bullets": bullets_by_id.get(key) or [b for b in (p.bullets or [])][:MAX_BULLETS]})
    seen = {s.lower() for s in out_sk}
    out_sk += [s for s in skills if s.lower() not in seen]
    resume = {"summary": summary.strip()[:900], "skills": out_sk, "roles": roles, "ai": True}
    letter = letter.strip()[:4000] if len(letter.strip()) >= 80 else ""
    return (resume, letter), None


def plain_cover_letter(user, positions, job) -> str:
    """No AI. Only facts from the profile; the user edits it on the Apply page."""
    from api.ats import years_of_experience
    ps = _ordered(positions)
    cos = list(dict.fromkeys(p.company for p in ps))[:3]
    y = years_of_experience(ps) if ps else 0
    first = next((b for p in ps for b in (p.bullets or []) if isinstance(b, str) and b.strip()), "")
    parts = [f"Dear {job.company} hiring team,",
             f"I'm applying for the {job.title} role."
             + (f" I bring {y} years of hands-on experience" + (f" across {', '.join(cos)}." if cos else ".") if y else "")]
    if ps and first:
        parts.append(f"Most recently, as {ps[0].role} at {ps[0].company}: {first.rstrip('.')}.")
    parts.append("I'd welcome the chance to talk about how my background fits what your team is building. "
                 "My resume is attached.")
    parts.append(f"Sincerely,\n{user.name or ''}".strip())
    return "\n\n".join(parts)


# ── PDF ─────────────────────────────────────────────────────────────────

def _latin(s: str) -> str:
    """The built-in PDF fonts are cp1252; keep what they can draw."""
    s = (s or "").replace("•", "-")
    return s.encode("cp1252", "replace").decode("cp1252")


def render_pdf(user, resume: dict) -> bytes:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem, HRFlowable
    from xml.sax.saxutils import escape

    E = lambda s: escape(_latin(str(s or "")))
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, leftMargin=0.7 * inch, rightMargin=0.7 * inch,
                            topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                            title=f"{user.name or 'Resume'} - Resume", author=user.name or "")
    ink = colors.HexColor("#1B1F2A")
    st = {
        "name": ParagraphStyle("n", fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=ink),
        "contact": ParagraphStyle("c", fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor("#4A5163")),
        "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=10.5, leading=14, spaceBefore=9,
                            textColor=ink),
        "body": ParagraphStyle("b", fontName="Helvetica", fontSize=9.5, leading=13, textColor=ink),
        "role": ParagraphStyle("r", fontName="Helvetica-Bold", fontSize=10, leading=13, spaceBefore=6, textColor=ink),
        "meta": ParagraphStyle("m", fontName="Helvetica-Oblique", fontSize=9, leading=12,
                               textColor=colors.HexColor("#4A5163")),
    }
    flow = [Paragraph(E(user.name or ""), st["name"])]
    contact = " | ".join(x for x in [user.email, user.phone, user.location, user.linkedin] if x)
    if user.headline:
        flow.append(Paragraph(E(user.headline), st["contact"]))
    if contact:
        flow.append(Paragraph(E(contact), st["contact"]))
    rule = lambda: HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#C9CEDA"), spaceBefore=2, spaceAfter=4)
    if resume.get("summary"):
        flow += [Paragraph("SUMMARY", st["h"]), rule(), Paragraph(E(resume["summary"]), st["body"])]
    if resume.get("skills"):
        flow += [Paragraph("SKILLS", st["h"]), rule(), Paragraph(E(", ".join(resume["skills"][:40])), st["body"])]
    if resume.get("roles"):
        flow += [Paragraph("EXPERIENCE", st["h"]), rule()]
        for r in resume["roles"]:
            flow.append(Paragraph(f"{E(r.get('role'))} - {E(r.get('company'))}", st["role"]))
            flow.append(Paragraph(E(" | ".join(x for x in [r.get("dates"), r.get("location")] if x)), st["meta"]))
            items = [ListItem(Paragraph(E(b), st["body"]), leftIndent=10) for b in (r.get("bullets") or [])]
            if items:
                flow.append(ListFlowable(items, bulletType="bullet", start="-", leftIndent=10, bulletFontSize=8))
    flow.append(Spacer(1, 4))
    doc.build(flow)
    return buf.getvalue()
