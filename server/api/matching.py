# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Per-job fit score for the signed-in seeker.

Everything here is derived from data that actually exists: the seeker's saved
skills, positions (dates -> years, titles), headline, work authorization and
work-style preference, against the job's extracted required skills, title,
experience range, visa flags and work mode. Nothing is invented and nothing
is padded: a signal that a job (or a profile) doesn't carry is left OUT of the
score rather than filled with a neutral guess, and `fit_reasons.basis` says
which signals were actually used.

    fit = round(100 * sum(weight_i * score_i) / sum(weight_i))   over available i

    skills      55  matched / required skills (job.required_skills)
    title       20  job title vs the seeker's position titles / headline
    experience  15  seeker's total years (overlaps merged) vs job exp range
    work mode   10  job.work_mode vs the seeker's work-style preference

A job needs at least a skills or a title signal to get a score at all; without
one `fit` is None for that job. A job that explicitly excludes every work
authorization the seeker holds scores 0 and is flagged as blocked.

Returns None for `fit` when the viewer is signed out or has no saved skills —
callers must then show no percentage anywhere.
"""
import datetime as dt
import re

from ingest.skills import extract_skills

W_SKILLS, W_TITLE, W_EXP, W_MODE = 55, 20, 15, 10

# seeker work_auth code -> the Job.visa_* column that speaks to it
AUTH_COL = {"usc": "usc", "gc": "gc", "h1b": "h1b", "opt": "opt", "cpt": "opt"}

# Canonicalisation: how people write the same skill differently.
_ALIAS = {
    "js": "javascript", "node": "javascript", "nodejs": "javascript", "node js": "javascript",
    "ts": "typescript", "postgres": "postgresql", "mongo": "mongodb", "k8s": "kubernetes",
    "cicd": "ci/cd", "ci cd": "ci/cd", "ci-cd": "ci/cd", "continuous integration": "ci/cd",
    "rest assured": "restassured", "rest-assured": "restassured",
    "restful": "rest", "rest api": "rest", "rest apis": "rest",
    "web driver io": "webdriverio", "webdriver io": "webdriverio",
    "gcp": "gcp", "google cloud": "gcp", "amazon web services": "aws",
    "scrum": "agile", "load testing": "performance testing",
    "automation testing": "test automation", "automated testing": "test automation",
    "etl": "etl testing", "tosca": "tricentis tosca",
    "c sharp": "c#", ".net": "c#", "dotnet": "c#",
    "github action": "github actions", "azure devops pipelines": "azure devops",
}
# Having the first genuinely implies having the second.
_IMPLIES = {"pyspark": {"spark"}, "restassured": {"rest", "api testing"},
            "postman": {"api testing"}}

_TOK = re.compile(r"[a-z0-9#+/.]+")


def _canon(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip().lower())
    return _ALIAS.get(s, s)


def _has_word(hay: str, needle: str) -> bool:
    return bool(needle) and re.search(r"(?<![a-z0-9#+])" + re.escape(needle) + r"(?![a-z0-9#+])", hay) is not None


# ── title tokens ─────────────────────────────────────────────
_SENIORITY = {"senior", "sr", "junior", "jr", "lead", "staff", "principal", "i", "ii", "iii", "iv",
              "associate", "entry", "level", "the", "a", "an", "and", "of", "for", "with", "in",
              "remote", "hybrid", "onsite", "contract", "contractor", "fulltime", "full", "time",
              "us", "usa", "w2", "c2c", "or", "to", "at", "-", "/"}
# words that carry almost no role information on their own
_GENERIC = {"engineer", "developer", "analyst", "specialist", "consultant", "professional",
            "engineering", "software", "technical", "technology", "it", "ii", "iii"}
_TITLE_SYN = {"tester": "qa", "testing": "qa", "test": "qa", "quality": "qa", "assurance": "qa",
              "qe": "qa", "qa": "qa", "sdet": "sdet", "automation": "automation",
              "automated": "automation", "swe": "software"}


def _title_tokens(t: str) -> set:
    toks = [w.strip("./+-") for w in _TOK.findall((t or "").lower())]
    toks = [_TITLE_SYN.get(w, w) for w in toks if w and w not in _SENIORITY]
    core = {w for w in toks if w not in _GENERIC}
    out = core or set(toks)
    if "sdet" in out:                      # SDET is literally "QA automation engineer"
        out |= {"qa", "automation"}
    return out


def _title_score(job_title: str, my_titles: list):
    jt = _title_tokens(job_title)
    if not jt or not my_titles:
        return None
    best = 0.0
    for t in my_titles:
        mt = _title_tokens(t)
        if mt:
            best = max(best, len(jt & mt) / len(jt))
    return best


# ── experience ───────────────────────────────────────────────
def years_of_experience(positions, today=None) -> float:
    """Total years across positions, with overlapping roles counted once."""
    today = today or dt.date.today()
    spans = []
    for p in positions:
        s = getattr(p, "started_on", None)
        if not s:
            continue
        e = getattr(p, "finished_on", None) or today
        if e >= s:
            spans.append((s, e))
    spans.sort()
    days, cur_s, cur_e = 0, None, None
    for s, e in spans:
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                days += (cur_e - cur_s).days
            cur_s, cur_e = s, e
        elif e > cur_e:
            cur_e = e
    if cur_e is not None:
        days += (cur_e - cur_s).days
    return round(days / 365.25, 1)


def _exp_score(years, lo, hi):
    if years is None or (lo is None and hi is None):
        return None
    lo = lo or 0
    if years < lo:
        return max(0.0, 1 - (lo - years) / max(lo, 1))
    if hi and years > hi:
        return max(0.7, 1 - 0.05 * (years - hi))       # over-qualified: mild, never a blocker
    return 1.0


# ── the profile snapshot ─────────────────────────────────────
class Profile:
    """Everything the scorer needs, loaded once per request."""

    def __init__(self, skills, positions, headline, work_auth, work_style, extra_titles=()):
        self.skills = [s for s in (skills or []) if s and s.strip()]
        canon = {_canon(s) for s in self.skills}
        # Skills the seeker demonstrably USES in their own position bullets
        # count too — but only when they already saved at least one skill.
        for p in positions or []:
            for s in extract_skills(getattr(p, "role", ""), " ".join(getattr(p, "bullets", None) or [])):
                canon.add(_canon(s))
        for s in list(canon):
            canon |= _IMPLIES.get(s, set())
        self.canon = canon
        self.joined = " | ".join(sorted(canon))
        self.titles = [t for t in ([getattr(p, "role", "") for p in positions or []]
                                   + [headline or ""] + list(extra_titles or [])) if t and t.strip()]
        self.years = years_of_experience(positions or []) if positions else None
        self.auth_cols = sorted({AUTH_COL[a] for a in (work_auth or []) if a in AUTH_COL})
        self.auth_names = [a for a in (work_auth or []) if a in AUTH_COL]
        self.work_style = work_style or ""

    @property
    def has_skills(self) -> bool:
        return bool(self.skills)

    def knows(self, job_skill: str) -> bool:
        c = _canon(job_skill)
        return c in self.canon or _has_word(self.joined, c)


def load_profile(db, user):
    """Profile for a signed-in seeker, or None (signed out / no saved skills)."""
    if user is None:
        return None
    from api.models import UserSkill, Position, AutopilotConfig
    skills = [r.skill for r in db.query(UserSkill).filter(UserSkill.user_id == user.id).all()]
    if not skills:
        return None
    positions = db.query(Position).filter(Position.user_id == user.id).all()
    cfg = db.get(AutopilotConfig, user.id)
    return Profile(skills, positions, user.headline, list(user.work_auth or []),
                   getattr(cfg, "work_style", "") if cfg else "",
                   list(getattr(cfg, "titles", None) or []) if cfg else [])


# ── scoring ──────────────────────────────────────────────────
def score_job(p: Profile, j) -> dict:
    """{'fit': int|None, 'fit_reasons': {...}} for one Job row (or duck-type)."""
    if p is None:
        return {"fit": None, "fit_reasons": None}

    req = [s for s in (j.required_skills or []) if s]
    matched = [s for s in req if p.knows(s)]
    missing = [s for s in req if s not in matched]

    parts, basis = [], []            # (weight, 0..1)
    if req:
        parts.append((W_SKILLS, len(matched) / len(req))); basis.append("skills")
    ts = _title_score(j.title, p.titles)
    if ts is not None:
        parts.append((W_TITLE, ts)); basis.append("title")
    es = _exp_score(p.years, j.exp_min, j.exp_max)
    if es is not None:
        parts.append((W_EXP, es)); basis.append("experience")
    mode_note = None
    if p.work_style and j.work_mode in ("remote", "hybrid", "onsite"):
        ok = p.work_style == j.work_mode or (p.work_style == "hybrid" and j.work_mode == "remote")
        parts.append((W_MODE, 1.0 if ok else 0.0)); basis.append("work_mode")
        mode_note = "matches your preference" if ok else f"you prefer {p.work_style}"

    # Visa: an explicit 'n' for EVERY status the seeker holds is a hard mismatch.
    flags = {"usc": j.visa_usc, "gc": j.visa_gc, "h1b": j.visa_h1b, "opt": j.visa_opt}
    mine = [flags.get(c) or "u" for c in p.auth_cols]
    blocked = bool(mine) and all(v == "n" for v in mine)
    visa = None
    if mine:
        visa = "blocked" if blocked else ("stated_yes" if "y" in mine else "not_stated")

    reasons = {"matched_skills": matched, "missing_skills": missing, "basis": basis,
               "title_match": None if ts is None else round(ts, 2),
               "years": p.years, "job_exp": {"min": j.exp_min, "max": j.exp_max},
               "work_mode": mode_note, "visa": visa, "blocked": blocked}

    if blocked:
        return {"fit": 0, "fit_reasons": reasons}
    if not ({"skills", "title"} & set(basis)):
        return {"fit": None, "fit_reasons": reasons}       # nothing meaningful to compare
    tot = sum(w for w, _ in parts)
    fit = round(100 * sum(w * s for w, s in parts) / tot)
    return {"fit": max(0, min(100, fit)), "fit_reasons": reasons}
