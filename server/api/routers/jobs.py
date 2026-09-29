# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session
from api.db import get_db
from api.auth import optional_user
from api.models import Job, Connection
from api.matching import load_profile, score_job
from ingest.quality import ATS_SOURCES

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
MAX_SCORED = 5000
VISA_COL = {"usc": Job.visa_usc, "gc": Job.visa_gc, "h1b": Job.visa_h1b, "opt": Job.visa_opt}


@router.get("")
def list_jobs(
    q: str = "", auth: str = "any",
    fields: str = "", families: str = "", employment: str = "",
    modes: str = "", company: str = "",
    fresh_days: int = 0, hide_reposts: bool = False,
    limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
    sort: str = "match", min_fit: int = Query(0, ge=0, le=100),
    db: Session = Depends(get_db), user=Depends(optional_user),
):
    Q = db.query(Job).filter(Job.active.is_(True))

    if q:
        like = f"%{q.lower()}%"
        Q = Q.filter(or_(Job.title.ilike(like), Job.company.ilike(like),
                         Job.description.ilike(like)))

    # Visa: hide only postings that EXPLICITLY exclude this status.
    # 'u' (not stated) stays visible — most postings say nothing, and
    # hiding them would delete ~70% of the board.
    if auth != "any" and auth in VISA_COL:
        Q = Q.filter(VISA_COL[auth] != "n")

    def csv(s): return [x for x in s.split(",") if x]
    if csv(fields):     Q = Q.filter(Job.career_field.in_(csv(fields)))
    if csv(families):   Q = Q.filter(Job.role_family.in_(csv(families)))
    if csv(employment): Q = Q.filter(Job.employment.in_(csv(employment)))
    if csv(modes):      Q = Q.filter(Job.work_mode.in_(csv(modes)))
    if csv(company):
        opts = []
        if "f500" in csv(company):     opts.append(Job.is_fortune500.is_(True))
        if "employer" in csv(company): opts.append(Job.company_type == "employer")
        if "staffing" in csv(company): opts.append(Job.company_type == "staffing")
        if opts: Q = Q.filter(or_(*opts))

    if fresh_days:
        import datetime as dt
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=fresh_days)
        Q = Q.filter(Job.posted_at >= cutoff)
    if hide_reposts:
        Q = Q.filter(Job.seen_count < 3)

    # Fit is per-viewer and computed here from real profile data. It is None for
    # signed-out viewers and for seekers with no saved skills; then nothing below
    # sorts or filters on it.
    prof = load_profile(db, user)
    if prof is not None and (sort == "match" or min_fit):
        # Score the whole filtered set, order/filter on the score, then page.
        # Bounded: the board holds hundreds of rows, not millions.
        scored = []
        for j in Q.order_by(Job.first_seen.desc()).limit(MAX_SCORED).all():
            r = score_job(prof, j)
            if min_fit and (r["fit"] is None or r["fit"] < min_fit):
                continue
            scored.append((j, r))
        if sort == "match":
            scored.sort(key=lambda t: -1 if t[1]["fit"] is None else t[1]["fit"], reverse=True)
        total = len(scored)
        page = scored[offset:offset + limit]
        rows = [j for j, _ in page]
        fits = {j.fingerprint: r for j, r in page}
    else:
        total = Q.count()
        Q = Q.order_by(Job.posted_at.desc() if sort == "new" else Job.first_seen.desc())
        rows = Q.offset(offset).limit(limit).all()
        fits = {j.fingerprint: score_job(prof, j) for j in rows}

    # referral paths — a referral beats any cover letter
    refs = {}
    if user:
        for c in db.query(Connection).filter(Connection.user_id == user.id).all():
            refs.setdefault(c.company, []).append({"name": c.name, "role": c.role, "degree": c.degree})

    return {"total": total, "offset": offset, "limit": limit,
            "fit_available": prof is not None,
            "jobs": [_shape(j, refs.get(j.company, []), fits.get(j.fingerprint)) for j in rows]}


@router.get("/{fingerprint}")
def get_job(fingerprint: str, db: Session = Depends(get_db), user=Depends(optional_user)):
    j = db.query(Job).get(fingerprint)
    if not j:
        raise HTTPException(404, "Job not found")
    refs = []
    if user:
        refs = [{"name": c.name, "role": c.role, "degree": c.degree}
                for c in db.query(Connection).filter(
                    Connection.user_id == user.id, Connection.company == j.company).all()]
    prof = load_profile(db, user)
    d = _shape(j, refs, score_job(prof, j))
    d["description"] = j.description
    return d


def _aware(d):
    """SQLite hands back naive datetimes; Postgres returns aware ones.
    Normalise so date maths works on both."""
    import datetime as dt
    if d is None: return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def _shape(j: Job, refs, fit=None):
    # Competition is ESTIMATED from age + repost breadth. No board publishes
    # exact applicant counts — inventing one is the fastest way to lose trust.
    import datetime as dt
    seen = _aware(j.first_seen)
    age = (dt.datetime.now(dt.timezone.utc) - seen).days if seen else 0
    comp = "lo" if age <= 2 and j.seen_count == 1 else "hi" if age > 14 or j.seen_count >= 3 else "md"
    return {
        "fingerprint": j.fingerprint, "company": j.company, "title": j.title,
        "location": j.location, "work_mode": j.work_mode, "employment": j.employment,
        "company_type": j.company_type, "is_fortune500": j.is_fortune500,
        "apply_url": j.apply_url,
        "comp": {"min": j.comp_min, "max": j.comp_max, "unit": j.comp_unit},
        "exp": {"min": j.exp_min, "max": j.exp_max},
        "visa": {"usc": j.visa_usc, "gc": j.visa_gc, "h1b": j.visa_h1b, "opt": j.visa_opt},
        "role_family": j.role_family, "career_field": j.career_field,
        "skills": j.required_skills or [],
        "days_live": age, "seen_count": j.seen_count, "relisted": j.relisted,
        "competition": comp, "referrals": refs,
        # Per-viewer fit: null (no percentage anywhere) when signed out / no skills.
        "fit": fit["fit"] if fit else None,
        "fit_reasons": fit["fit_reasons"] if fit else None,
        # `verified` is true ONLY if our own request to apply_url succeeded
        # (2xx/3xx). Never inferred from the source. `direct` means the posting
        # came straight from the company's own ATS careers board.
        "verified": j.link_status == "ok" and j.verified_at is not None,
        "verified_at": j.verified_at.isoformat() if j.verified_at else None,
        "link_status": j.link_status,
        "source": j.source, "direct": j.source in ATS_SOURCES,
    }
