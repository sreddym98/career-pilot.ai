# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Employer application questions, read from the ATS's own public API.

Normalised to one shape the Apply page and the extension both speak:

    {"id", "label", "type": text|textarea|select|multi|file|boolean,
     "required", "options": [str], "eeo": bool}

Greenhouse publishes the full form (boards-api ...?questions=true). Lever's
public posting API has no custom questions, so for Lever we return its
standard, documented form fields and say the list is partial. Ashby has no
documented public form API, so it is {supported: false}. Nothing here ever
raises on a network or parsing problem: the caller gets {supported: false}.

prefill() answers what it can from REAL profile data only. Anything else is
left blank with needs_you=true; EEO/demographic questions are never guessed.
"""
import datetime as dt
import re

import requests

TIMEOUT = 8
TTL = dt.timedelta(hours=24)
UA = {"User-Agent": "careerpilot.ai apply helper (+https://careerpilot.ai)"}

EEO_RX = re.compile(r"gender|race|ethnic|hispanic|latino|veteran|disabilit|sexual orientation|"
                    r"transgender|pronoun|demographic|self[- ]identif", re.I)


# ── which posting is this? ───────────────────────────────────────────────

_GH = re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_app\?for=)?([A-Za-z0-9_-]+)/jobs/(\d+)", re.I)
_GH_EMBED = re.compile(r"greenhouse\.io/embed/job_app\?(?:.*&)?for=([A-Za-z0-9_-]+)(?:.*&)?token=(\d+)", re.I)
_GH_JID = re.compile(r"[?&]gh_jid=(\d+)", re.I)
_LEVER = re.compile(r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9_.-]+)/([0-9a-f-]{36})", re.I)
_ASHBY = re.compile(r"jobs\.ashbyhq\.com/([^/?#]+)/([0-9a-f-]{36})", re.I)


def _board_for_label(source: str, company: str) -> str | None:
    """Ingest stores the company LABEL, not the board slug. For postings
    whose apply URL is on the employer's own domain, look the slug up in the
    same companies.yaml ingest reads."""
    try:
        from ingest.run import load_boards
        for sec, slug, label in load_boards():
            if sec == source and label.strip().lower() == (company or "").strip().lower():
                return slug
    except Exception:
        pass
    return None


def ref_for(job) -> dict | None:
    """{"ats", "board", "id"} for a posting, or None if we can't tell."""
    url = job.apply_url or ""
    m = _GH.search(url) or _GH_EMBED.search(url)
    if m:
        return {"ats": "greenhouse", "board": m.group(1), "id": m.group(2)}
    m = _LEVER.search(url)
    if m:
        return {"ats": "lever", "board": m.group(1), "id": m.group(2)}
    m = _ASHBY.search(url)
    if m:
        return {"ats": "ashby", "board": m.group(1), "id": m.group(2)}
    if job.source == "greenhouse":
        jid = (_GH_JID.search(url).group(1) if _GH_JID.search(url) else None) or job.source_id
        board = _board_for_label("greenhouse", job.company)
        if jid and board and str(jid).isdigit():
            return {"ats": "greenhouse", "board": board, "id": str(jid)}
    if job.source in ("lever", "ashby") and job.source_id:
        board = _board_for_label(job.source, job.company)
        if board:
            return {"ats": job.source, "board": board, "id": job.source_id}
    return None


# ── normalisers (pure; tested against recorded fixtures) ─────────────────

def _yes_no(opts: list[str]) -> bool:
    low = sorted(o.strip().lower() for o in opts)
    return low == ["no", "yes"]


def normalize_greenhouse(data: dict) -> list[dict]:
    """GET boards-api.greenhouse.io/v1/boards/{board}/jobs/{id}?questions=true.
    `questions` holds the main form; `location_questions` a location block;
    `compliance` and `demographic_questions` the EEO sections."""
    out, seen = [], set()

    def add(q):
        if q["id"] and q["id"] not in seen:
            seen.add(q["id"]); out.append(q)

    for q in (data.get("questions") or []) + (data.get("location_questions") or []):
        fields = q.get("fields") or []
        if not fields:
            continue
        label = (q.get("label") or "").strip()
        f = next((x for x in fields if x.get("type") == "input_file"), fields[0])
        t = f.get("type")
        opts = [str(v.get("label", "")).strip() for v in (f.get("values") or []) if str(v.get("label", "")).strip()]
        typ = {"input_text": "text", "textarea": "textarea", "input_file": "file",
               "multi_value_single_select": "select", "multi_value_multi_select": "multi"}.get(t)
        if typ is None:
            continue                              # input_hidden and anything new
        if typ == "select" and _yes_no(opts):
            typ = "boolean"
        add({"id": str(f.get("name") or ""), "label": label, "type": typ,
             "required": bool(q.get("required")), "options": opts,
             "eeo": bool(EEO_RX.search(label))})

    for sec in data.get("compliance") or []:
        for q in sec.get("questions") or []:
            for f in q.get("fields") or []:
                opts = [str(v.get("label", "")).strip() for v in (f.get("values") or []) if v.get("label")]
                add({"id": str(f.get("name") or ""), "label": (q.get("label") or "").strip(),
                     "type": "select", "required": bool(q.get("required")), "options": opts, "eeo": True})

    demo = data.get("demographic_questions") or {}
    for q in demo.get("questions") or []:
        opts = [str(o.get("label", "")).strip() for o in (q.get("answer_options") or []) if o.get("label")]
        typ = "multi" if q.get("type") == "multi_value_multi_select" else "select"
        add({"id": f"demographic_{q.get('id')}", "label": (q.get("label") or "").strip(), "type": typ,
             "required": bool(q.get("required")), "options": opts, "eeo": True})
    return out


# Lever's apply form is the same on every posting, documented at
# https://github.com/lever/postings-api#apply-to-a-job-posting . Custom
# "additional questions" are not in the public API.
LEVER_FORM = [
    {"id": "resume", "label": "Resume/CV", "type": "file", "required": True},
    {"id": "name", "label": "Full name", "type": "text", "required": True},
    {"id": "email", "label": "Email", "type": "text", "required": True},
    {"id": "phone", "label": "Phone", "type": "text", "required": False},
    {"id": "location", "label": "Current location", "type": "text", "required": False},
    {"id": "org", "label": "Current company", "type": "text", "required": False},
    {"id": "urls[LinkedIn]", "label": "LinkedIn URL", "type": "text", "required": False},
    {"id": "urls[GitHub]", "label": "GitHub URL", "type": "text", "required": False},
    {"id": "urls[Portfolio]", "label": "Portfolio URL", "type": "text", "required": False},
    {"id": "comments", "label": "Additional information", "type": "textarea", "required": False},
]


def normalize_lever(data: dict) -> list[dict]:
    """The posting itself (GET api.lever.co/v0/postings/{site}/{id}) only
    proves it exists; the questions are Lever's standard form."""
    if not isinstance(data, dict) or not data.get("id"):
        return []
    return [{**q, "options": [], "eeo": False} for q in LEVER_FORM]


# Used when the employer's form can't be read: the questions nearly every
# application asks. The extension flags anything else it finds on the page.
STANDARD_FORM = [
    {"id": "first_name", "label": "First name", "type": "text", "required": True},
    {"id": "last_name", "label": "Last name", "type": "text", "required": True},
    {"id": "email", "label": "Email", "type": "text", "required": True},
    {"id": "phone", "label": "Phone", "type": "text", "required": False},
    {"id": "location", "label": "Location (city)", "type": "text", "required": False},
    {"id": "linkedin", "label": "LinkedIn profile", "type": "text", "required": False},
    {"id": "resume", "label": "Resume/CV", "type": "file", "required": True},
    {"id": "cover_letter", "label": "Cover letter", "type": "file", "required": False},
    {"id": "work_authorized", "label": "Are you legally authorized to work in the United States?",
     "type": "boolean", "required": True},
    {"id": "sponsorship", "label": "Will you now or in the future require sponsorship for employment visa status (e.g. H-1B)?",
     "type": "boolean", "required": True},
]


def standard_questions() -> list[dict]:
    return [{**q, "options": ["Yes", "No"] if q["type"] == "boolean" else [], "eeo": False}
            for q in STANDARD_FORM]


# ── fetching (live; not reachable from the test sandbox) ─────────────────

def _fetch(ref: dict) -> dict:
    try:
        if ref["ats"] == "greenhouse":
            r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{ref['board']}/jobs/{ref['id']}",
                             params={"questions": "true"}, headers=UA, timeout=TIMEOUT)
            if r.status_code != 200:
                return {"supported": False, "ats": "greenhouse", "reason": f"http_{r.status_code}"}
            qs = normalize_greenhouse(r.json())
            return {"supported": bool(qs), "ats": "greenhouse", "partial": False, "questions": qs}
        if ref["ats"] == "lever":
            r = requests.get(f"https://api.lever.co/v0/postings/{ref['board']}/{ref['id']}",
                             headers=UA, timeout=TIMEOUT)
            if r.status_code != 200:
                return {"supported": False, "ats": "lever", "reason": f"http_{r.status_code}"}
            qs = normalize_lever(r.json())
            return {"supported": bool(qs), "ats": "lever", "partial": True, "questions": qs}
        return {"supported": False, "ats": ref["ats"], "reason": "no_public_form_api"}
    except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError) as e:
        return {"supported": False, "ats": ref.get("ats"), "reason": f"unreachable: {type(e).__name__}"}


def questions_for(db, job) -> dict:
    """Cached 24h per posting. Failures are not cached, so a blip retries."""
    from api.models import ATSQuestions
    now = dt.datetime.now(dt.timezone.utc)
    row = db.get(ATSQuestions, job.fingerprint)
    if row is not None:
        at = row.fetched_at if row.fetched_at.tzinfo else row.fetched_at.replace(tzinfo=dt.timezone.utc)
        if now - at < TTL:
            return {**row.result, "cached": True}
    ref = ref_for(job)
    if not ref:
        return {"supported": False, "ats": None, "reason": "unknown_ats"}
    got = _fetch(ref)
    if got.get("supported"):
        try:
            db.merge(ATSQuestions(fingerprint=job.fingerprint, result=got, fetched_at=now))
            db.commit()
        except Exception:
            db.rollback()
    return got


# ── pre-filling from the profile ─────────────────────────────────────────

AUTH_LABEL = {"usc": "U.S. citizen", "gc": "Green card holder", "h1b": "H-1B", "opt": "OPT/EAD", "cpt": "CPT"}
NEEDS_SPONSOR = {"h1b", "opt", "cpt"}


def years_of_experience(positions) -> int:
    """Whole years, overlapping roles counted once."""
    months = set()
    for p in positions:
        end = p.finished_on or dt.date.today()
        y, m = p.started_on.year, p.started_on.month
        while (y, m) <= (end.year, end.month):
            months.add((y, m))
            m += 1
            if m > 12:
                y, m = y + 1, 1
    return len(months) // 12


def _pick(options: list[str], want: str) -> str | None:
    """The option whose label means `want` ("yes", "no", a number, "decline")."""
    if not options:
        return None
    w = want.lower()
    if w in ("yes", "no"):
        for o in options:
            if re.match(rf"^\s*{w}\b", o, re.I):
                return o
        return None
    if w == "decline":
        for o in options:
            if re.search(r"decline|prefer not|don.?t wish|do not wish|not to (say|answer|disclose)|choose not", o, re.I):
                return o
        return None
    if w.isdigit():                                      # years: "5-7 years", "10+"
        n = int(w)
        for o in options:
            nums = [int(x) for x in re.findall(r"\d+", o)]
            if len(nums) >= 2 and nums[0] <= n <= nums[1]:
                return o
            if len(nums) == 1 and ("+" in o or "more" in o.lower()) and n >= nums[0]:
                return o
            if len(nums) == 1 and re.search(r"less|under|fewer|<", o, re.I) and n < nums[0]:
                return o
            if len(nums) == 1 and nums[0] == n:
                return o
    return None


def profile_facts(user, positions) -> dict:
    ps = sorted(positions, key=lambda p: p.started_on, reverse=True)
    cur = next((p for p in ps if p.finished_on is None), None)
    name = (user.name or "").strip()
    first, _, last = name.partition(" ")
    auth = [a for a in (user.work_auth or []) if a in AUTH_LABEL]
    return {"full_name": name, "first_name": first, "last_name": last.strip(),
            "email": user.email or "", "phone": user.phone or "", "location": user.location or "",
            "linkedin": user.linkedin or "", "headline": user.headline or "",
            "current_company": cur.company if cur else "", "current_title": cur.role if cur else "",
            "years": years_of_experience(ps) if ps else None,
            "work_auth": auth,
            "authorized": True if auth else None,
            "needs_sponsorship": (any(a in NEEDS_SPONSOR for a in auth)) if auth else None}


# (field, regex on id+label). First match wins; order matters.
RULES = [
    ("resume",        r"\bresume\b|\bcv\b|curriculum"),
    ("cover_letter",  r"cover[\s_-]?letter"),
    ("sponsorship",   r"sponsor|visa status|require.*visa|h-?1b"),
    ("authorized",    r"authori[sz]ed to work|legally (authori[sz]ed|eligible|able)|eligib\w* to work|right to work|work authori[sz]ation"),
    ("salary",        r"salary|compensation|pay expectation|desired (pay|rate)|expected (pay|ctc|rate)"),
    ("first_name",    r"^first[\s_-]?name|preferred first|given name|\bfirst_name\b"),
    ("last_name",     r"^last[\s_-]?name|family name|surname|\blast_name\b"),
    ("full_name",     r"^(full[\s_-]?)?name\b|^name$|legal name|\bfull name\b"),
    ("email",         r"e-?mail"),
    ("phone",         r"phone|mobile|telephone"),
    ("linkedin",      r"linked[\s_-]?in"),
    ("years",         r"years of (professional |relevant |total )?experience|how many years"),
    ("current_company", r"current (company|employer)|^org$|most recent (company|employer)|\borg\b"),
    ("current_title", r"current (job )?title|current role|most recent (job )?title"),
    ("location",      r"^location|current location|city|where are you (located|based)"),
]


def _classify(q: dict) -> str | None:
    hay = f"{q.get('id', '')} | {q.get('label', '')}"
    for field, rx in RULES:
        if re.search(rx, hay, re.I):
            return field
    return None


def prefill(questions: list[dict], facts: dict, has_cover_letter: bool = True) -> list[dict]:
    """Each question gets: value, source ('profile' | 'derived' | 'file' | ''),
    needs_you (True = the user must answer it), note."""
    out = []
    for q in questions:
        q = dict(q)
        opts = q.get("options") or []
        val, src, note = "", "", ""
        if q.get("eeo"):
            dec = _pick(opts, "decline")
            val, src = (dec or ""), ("decline" if dec else "")
            note = "Voluntary. Left as decline to answer; change it if you want to."
            q.update(value=val, source=src, needs_you=bool(q.get("required") and not val), note=note)
            out.append(q); continue
        field = _classify(q)
        if field == "resume" and q.get("type") in ("file", "textarea"):
            val, src, note = "tailored_resume.pdf", "file", "Your tailored resume is attached"
        elif field == "cover_letter":
            if has_cover_letter:
                val, src, note = "cover_letter", "file", "Your cover letter below"
        elif field == "authorized" and facts.get("authorized") is not None:
            want = "yes" if facts["authorized"] else "no"
            val = _pick(opts, want) if opts else want.capitalize()
            src = "derived" if val else ""
            note = f"From your work authorization ({', '.join(AUTH_LABEL[a] for a in facts['work_auth'])})"
        elif field == "sponsorship" and facts.get("needs_sponsorship") is not None:
            want = "yes" if facts["needs_sponsorship"] else "no"
            hay = f"{q.get('id', '')} {q.get('label', '')}"
            if re.search(r"without (the )?(need (for|of) )?(any )?(visa )?sponsor", hay, re.I):
                want = "no" if facts["needs_sponsorship"] else "yes"   # "authorized ... without sponsorship?"
            if q.get("type") in ("text", "textarea"):
                val = ("Yes. " if facts["needs_sponsorship"] else "No. ") + \
                      f"Current status: {', '.join(AUTH_LABEL[a] for a in facts['work_auth'])}."
            else:
                val = _pick(opts, want) if opts else want.capitalize()
            src = "derived" if val else ""
            note = f"From your work authorization ({', '.join(AUTH_LABEL[a] for a in facts['work_auth'])})"
        elif field == "years" and facts.get("years") is not None:
            y = str(facts["years"])
            val = (_pick(opts, y) or "") if opts else y
            src = "derived" if val else ""
            note = "Counted from the dates of the roles on your profile"
        elif field == "salary":
            note = "You decide this number"
        elif field in ("first_name", "last_name", "full_name", "email", "phone", "linkedin",
                       "current_company", "current_title", "location") and not opts:
            val = facts.get(field) or ""
            src = "profile" if val else ""
        if q.get("type") in ("select", "boolean", "multi") and val and opts and val not in opts:
            val, src = "", ""
        q.update(value=val, source=src, needs_you=not val, note=note)
        if not val and not note:
            q["note"] = "You answer this"
        out.append(q)
    return out


def checklist(answers: list[dict]) -> dict:
    """Counts the Apply page shows ("Ready: 9 of 11 answered"). EEO questions
    are voluntary and left out of the count."""
    core = [a for a in answers if not a.get("eeo")]
    done = [a for a in core if str(a.get("value") or "").strip()]
    req_open = [a for a in answers if a.get("required") and not str(a.get("value") or "").strip()]
    return {"answered": len(done), "total": len(core), "required_open": len(req_open),
            "ready": not req_open}
