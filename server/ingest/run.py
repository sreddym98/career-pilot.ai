# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""The ingest runner.

    python ingest/run.py --once        one full pass, all sources (scheduled job)
    python ingest/run.py --fast        aggregators only — new contract roles
    python ingest/run.py --loop        continuous, tier-scheduled (local use)
    python ingest/run.py --report      volume, freshness, gaps vs targets (no network)
    python ingest/run.py --prune       drop jobs unseen for --prune-days (default 45)

Scheduled-job contract (GitHub Actions):
    exit 0   run completed (individual boards may have failed — see summary line)
    exit 1   every source that was attempted failed
    exit 2   database unreachable / fatal setup error
    --max-seconds N   stop fetching in time to exit cleanly (default 1000s when
                      GITHUB_ACTIONS is set, so the 20 min workflow limit is never hit)

Deactivation safety: a job is deactivated only when ITS OWN source was fetched
successfully this run and it is absent from that fetch. Failed, empty, partial
or timed-out fetches never deactivate anything.

Targets it reports against: 100+ live full-time, 200+ live contract.
It will tell you plainly when you're short and what to add.
"""
import argparse, hashlib, os, re, sys, time, datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed

SERVER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if __package__ in (None, ""):
    # Direct execution makes this file's directory first on sys.path, which
    # otherwise resolves `ingest` to ingest.py instead of the package.
    sys.path = [path for path in sys.path if path != os.path.dirname(os.path.abspath(__file__))]
    sys.path.insert(0, SERVER_ROOT)

import random
from sqlalchemy import select, text

from ingest import sources, scheduler
from ingest.visa_parse import parse_visa
from ingest.skills import extract_skills
from ingest import quality, verify
try:
    from api.db import SessionLocal, init_db
    from api.models import Job, Application
except Exception as _e:          # e.g. ENV=prod with a SQLite DATABASE_URL
    print(f"FATAL: cannot initialise database layer: {_e}", file=sys.stderr)
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))

TARGET_FULLTIME = 100
TARGET_CONTRACT = 200

# What we actually want. Everything else from a board gets dropped at ingest —
# a QA-focused portal full of sales roles is worse than a small one.
WANTED = re.compile(
    r"\b(sdet|qa|quality engineer|quality assurance|test engineer|test automation|"
    r"automation engineer|software engineer in test|test architect|test lead|"
    r"performance engineer|etl test|data quality|quality analyst|qe\b|"
    r"test manager|automation test|testing engineer)\b", re.I)

# Broader net for the aggregator leg, where titles are messier
WANTED_LOOSE = re.compile(r"\b(sdet|qa|test|quality|automation)\b", re.I)
PLACEHOLDER_TITLE = re.compile(
    r"^(test|test job|test job title|test req|quality checker|qa tester entry level)$", re.I)

AGG_QUERIES = [
    "SDET jobs in USA", "QA automation engineer jobs in USA",
    "software development engineer in test USA", "test automation engineer contract USA",
    "ETL tester jobs in USA", "performance test engineer USA",
    "QA engineer c2c contract USA", "automation testing corp to corp USA",
]

STOP = {"senior", "sr", "jr", "junior", "lead", "staff", "principal", "i", "ii", "iii", "iv",
        "the", "a", "an", "and", "of", "for", "with", "remote", "hybrid", "onsite", "us", "usa"}
STATES = set("al ak az ar ca co ct de fl ga hi id il in ia ks ky la me md ma mi mn ms mo mt ne "
             "nv nh nj nm ny nc nd oh ok or pa ri sc sd tn tx ut vt va wa wv wi wy dc".split())


def norm(s):
    s = "".join(c if c.isalnum() or c.isspace() else " " for c in (s or "").lower())
    return " ".join(sorted(t for t in s.split() if t not in STOP))


def norm_loc(s):
    s = (s or "").lower()
    if "remote" in s:
        return "remote"
    parts = [p.strip() for p in s.replace("|", ",").split(",") if p.strip()]
    state = ""
    if parts:
        tail = "".join(c for c in parts[-1] if c.isalnum())
        if tail in STATES:
            state, parts = tail, parts[:-1]
    return "".join(c for c in " ".join(parts) if c.isalnum())[:24] + state


def fingerprint(co, title, loc, source="", source_id=""):
    """Keep each ATS posting distinct while still deduplicating repeated pulls.

    A company can publish the same title in multiple countries or remote
    regions. Title/location normalization alone merges those postings and can
    cause a single SQLAlchemy flush to insert duplicate primary keys.
    """
    stable_id = f"{source}|{source_id}" if source and source_id else f"{norm(co)}|{norm(title)}|{norm_loc(loc)}"
    return hashlib.sha256(stable_id.encode()).hexdigest()[:20]


STAFFING_SUB = ["staffing", "consulting", "consultancy", "infotech", "recruit", "placement",
                "talent", "resourcing", "manpower", "workforce", "technologies", "it services",
                "solutions inc", "systems inc", "global services", "e-solutions"]
STAFFING_PAT = [r"\bsource\b", r"net\d", r"\btek\b|tek$", r"\bsoft\b|soft$", r"\binc\.?$",
                r"\bllc$", r"\bgroup$", r"\bcorp(oration)?$", r"\bpartners?$", r"\bconsultants?$",
                r"\bsolutions?$", r"\bsystems?$", r"\bservices?$"]
STAFFING_TXT = ["our client", "client is seeking", "end client", "c2c", "corp to corp",
                "corp-to-corp", "w2 only", "submit your resume", "prime vendor", "implementation partner"]


def company_type(company, text=""):
    c = (company or "").lower().strip()
    t = (text or "").lower()[:3000]
    if sum(k in t for k in STAFFING_TXT) >= 2:
        return "staffing"
    if any(m in c for m in STAFFING_SUB) or any(re.search(p, c) for p in STAFFING_PAT):
        return "staffing"
    return "staffing" if any(k in t for k in STAFFING_TXT) else "employer"


def employment_of(text, hint=None):
    if hint:
        h = hint.lower()
        if any(k in h for k in ("contract", "temp", "c2c", "w2", "contractor")):
            return "contract"
        if "full" in h or "permanent" in h:
            return "fulltime"
    t = (text or "").lower()[:4000]
    c = sum(k in t for k in ["c2c", "corp to corp", "w2 contract", "contract role",
                             "contract position", "months contract", "month contract",
                             "1099", "contract to hire", "long term contract", "contract duration"])
    f = sum(k in t for k in ["full-time", "full time", "permanent position", "fte", "salaried",
                             "benefits package", "401k", "equity"])
    if c > f:
        return "contract"
    return "fulltime" if f else "unknown"


def work_mode(loc, text, remote_flag=None):
    if remote_flag:
        return "remote"
    s = f"{loc} {(text or '')[:1500]}".lower()
    if "hybrid" in s:
        return "hybrid"
    if "remote" in s or "work from home" in s:
        return "remote"
    if "onsite" in s or "on-site" in s or "in office" in s:
        return "onsite"
    return "onsite" if loc else "unknown"


def load_boards():
    path = os.path.join(HERE, "companies.yaml")
    out, section = [], None
    if not os.path.exists(path):
        return out
    for line in open(path, encoding="utf-8"):
        if line.strip().startswith("#") or not line.strip():
            continue
        m = re.match(r"^(\w+):", line)
        if m and not line.startswith(" "):
            section = m.group(1)
            continue
        m = re.match(r"^\s*-\s*\{slug:\s*([^,}]+),\s*label:\s*([^}]+)\}", line)
        if m and section in sources.ATS:
            out.append((section, m.group(1).strip(), m.group(2).strip()))
    return out


def _s(v):
    """Strip NUL bytes — Postgres text columns reject them, and scraped
    descriptions occasionally carry them."""
    return v.replace("\x00", "") if isinstance(v, str) else v


def _parse_dt(v):
    if not v:
        return None
    try:
        if isinstance(v, (int, float)):
            return dt.datetime.fromtimestamp(v / 1000 if v > 1e11 else v, dt.timezone.utc)
        d = dt.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def _aware(d):
    return d.replace(tzinfo=dt.timezone.utc) if d is not None and d.tzinfo is None else d


def upsert(db, rec, now, seen=None):
    """Insert or refresh one posting. Portable SQL only (ORM get/add).

    `seen` is the set of fingerprints already handled in this batch. The
    session runs with autoflush off, so db.get() cannot see rows added earlier
    in the same batch: without this a source that lists the same id twice (or
    two JSearch queries returning one job) inserts a duplicate primary key and
    the whole batch fails at commit.

    Returns "new" | "seen" | "relisted" | "dup" | None (rejected).
    """
    title = _s((rec.get("title") or "").strip())
    company = _s((rec.get("company") or "").strip())
    if not title or not company or PLACEHOLDER_TITLE.match(title):
        return None
    # Static quality gate: real https apply link, real title/company, not stale.
    # Rejected rows are never stored, so nothing unverifiable reaches the board.
    if quality.reject_reason(rec, _parse_dt(rec.get("posted_at")), now):
        return None
    apply_url = quality.normalize_apply_url(rec.get("url"))
    desc = _s(rec.get("description") or "")
    fp = fingerprint(company, title, rec.get("location", ""),
                     rec.get("source", ""), rec.get("source_id", ""))
    if seen is not None:
        if fp in seen:
            return "dup"
        seen.add(fp)
    row = db.get(Job, fp)

    if row:
        if row.link_status == "dead" and not row.active and apply_url == quality.normalize_apply_url(row.apply_url):
            # The link answered 404/410 and the source still shows the same URL:
            # keep it retired instead of resurrecting a dead posting each run.
            row.last_seen = now
            return "seen"
        last = _aware(row.last_seen)
        gap = (now - last).days if last else 0
        status = "relisted" if (gap >= 21 or not row.active) else "seen"
        row.last_seen = now              # first_seen is never touched
        row.seen_count = (row.seen_count or 1) + 1
        row.active = True
        if status == "relisted":
            row.relisted = True
        if apply_url and quality.normalize_apply_url(row.apply_url) != apply_url:
            # first real link, or the source moved the posting: take the new one
            # and forget any verification of the old one.
            row.apply_url = apply_url
            row.verified_at = row.link_checked_at = row.link_status = row.link_http = None
        if desc and desc[:20000] != (row.description or ""):
            # Refresh what is derived from the text (and backfill rows ingested
            # before skills extraction existed). Never blank a description a
            # connector didn't supply (SmartRecruiters).
            v = parse_visa(desc)
            row.description = desc[:20000]
            row.visa_usc, row.visa_gc, row.visa_h1b, row.visa_opt = v["usc"], v["gc"], v["h1b"], v["opt"]
        if not row.required_skills or desc:
            sk = extract_skills(title, desc)
            if sk or not row.required_skills:
                row.required_skills = sk
        if row.posted_at is None and rec.get("posted_at"):
            row.posted_at = _parse_dt(rec.get("posted_at"))
        return status

    v = parse_visa(desc)
    ct = company_type(company, desc)
    db.add(Job(
        fingerprint=fp, source=rec.get("source", ""), source_id=rec.get("source_id"),
        company=company, company_type=ct, title=title,
        location=_s(rec.get("location", "")),
        work_mode=work_mode(rec.get("location", ""), desc, rec.get("remote")),
        employment=employment_of(desc, rec.get("employment")),
        description=desc[:20000], apply_url=_s(apply_url),
        visa_usc=v["usc"], visa_gc=v["gc"], visa_h1b=v["h1b"], visa_opt=v["opt"],
        required_skills=extract_skills(title, desc),
        posted_at=_parse_dt(rec.get("posted_at")),
        first_seen=now, last_seen=now, seen_count=1, active=True))
    return "new"


def _zero():
    return {"new": 0, "relisted": 0, "seen": 0, "skipped": 0, "dup": 0, "bad": 0, "kept": 0,
            "rejected": 0}


def ingest_batch(db, recs, now, pat=WANTED):
    """Upsert one source's records and commit them together.

    If the batch fails to commit (one poisoned row), roll back and redo it row
    by row so a single bad record costs one record, not the source — and
    nothing is left half-committed.
    """
    def apply(rows, seen_for_row=None):
        st = _zero()
        seen = set()
        for rec in rows:
            if not pat.search(rec.get("title", "") or ""):
                st["skipped"] += 1
                continue
            r = upsert(db, rec, now, seen if seen_for_row is None else seen_for_row)
            if r is None:
                st["rejected"] += 1
                continue
            st["kept"] += 1 if r != "dup" else 0
            st[r] += 1
        return st

    try:
        st = apply(recs)
        db.commit()
        return st
    except Exception:
        db.rollback()
    st = _zero()
    for rec in recs:
        try:
            one = apply([rec], set())
            db.commit()
            for k, v in one.items():
                st[k] += v
        except Exception:
            db.rollback()
            st["bad"] += 1
    return st


def pull(fn, *a, **kw):
    """Run a connector to completion. Returns (records, error). Records
    fetched before a mid-stream failure are kept, but the error means the
    fetch does NOT count as a clean sweep."""
    recs, err = [], None
    try:
        for r in fn(*a, **kw):
            recs.append(r)
    except sources.DeadlineExceeded:
        err = "DeadlineExceeded"
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:100]}"
    return recs, err


def sweep_board(db, source, company, now, raw, kept):
    """Deactivate one board's jobs that were absent from a CLEAN full fetch.

    Skipped (returns 0, reason) when the fetch looks untrustworthy:
      - the board returned no postings at all (empty != "everything closed")
      - a board that had >=5 live matches now shows fewer than 20% of them
    """
    if raw < 1:
        return 0, "empty fetch"
    q = db.query(Job).filter(Job.source == source, Job.company == company,
                             Job.active.is_(True), Job.last_seen < now)
    prev = q.count()
    if prev == 0:
        return 0, ""
    if prev >= 5 and kept < max(1, 0.2 * prev):
        return 0, f"suspicious drop ({prev} live -> {kept} listed)"
    n = q.update({"active": False}, synchronize_session=False)
    db.commit()
    return n, ""


def _new_result(name, kind):
    return {"name": name, "kind": kind, "ok": False, "deferred": False, "raw": 0,
            "err": "", "swept": 0, "note": "", **_zero()}


def _finish(res, recs, err, st):
    res["raw"] = len(recs)
    for k, v in st.items():
        res[k] = v
    if err == "DeadlineExceeded":
        res["deferred"], res["err"] = True, "not fetched (time budget)"
    elif err:
        res["err"] = err
    elif st["bad"]:
        res["err"] = f"{st['bad']} rows failed to save"
    else:
        res["ok"] = True
    return res


def run_ats(db, now, boards, workers=8):
    """Fetch boards in parallel (network only); write from this thread only."""
    results = []
    boards = list(boards)
    random.shuffle(boards)       # so a time-boxed run rotates coverage
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(pull, sources.ATS[ats], slug, label): (ats, slug, label)
                for ats, slug, label in boards}
        for f in as_completed(futs):
            ats, slug, label = futs[f]
            res = _new_result(f"{ats}/{slug}", "ats")
            try:
                recs, err = f.result()
                recs = [r for r in recs if isinstance(r, dict)]
                st = ingest_batch(db, recs, now)
                _finish(res, recs, err, st)
                if res["ok"]:
                    n, why = sweep_board(db, ats, label.strip(), now, res["raw"], st["kept"])
                    res["swept"], res["note"] = n, why
            except Exception as e:           # never let one board kill the run
                db.rollback()
                res["err"] = f"{type(e).__name__}: {str(e)[:100]}"
            results.append(res)
    return results


def expire_aggregators(db, now, ok_sources, days):
    """Aggregator feeds are windows, not full listings, so absence proves
    nothing. Age out a source's rows only after `days` unseen AND only if that
    source fetched cleanly with results this run."""
    if not ok_sources:
        return 0
    cutoff = now - dt.timedelta(days=days)
    n = db.query(Job).filter(Job.source.in_(sorted(ok_sources)), Job.active.is_(True),
                             Job.last_seen < cutoff).update({"active": False},
                                                            synchronize_session=False)
    db.commit()
    return n


def _remotive_due(now):
    every = int(os.environ.get("INGEST_REMOTIVE_EVERY_HOURS", "6") or 6)
    return every <= 1 or now.hour % every == 0


def run_aggregators(db, now, expire_days=21, deadline=None):
    """Free sources run unconditionally. Keyed ones are skipped silently
    if the key is absent, and reported at the end so you know what you're
    missing rather than wondering why contract roles are thin."""
    results, missing = [], []
    src_ok, src_bad = set(), set()

    tasks = []
    if _remotive_due(now):     # Remotive asks for <= ~4 fetches/day
        tasks += [("remotive:qa", "remotive", sources.remotive, ("qa",)),
                  ("remotive:test", "remotive", sources.remotive, ("test",))]
    tasks += [("remoteok", "remoteok", sources.remoteok, ()),
              ("arbeitnow", "arbeitnow", sources.arbeitnow, ())]
    if os.environ.get("USAJOBS_KEY") and os.environ.get("USAJOBS_EMAIL"):
        tasks += [(f"usajobs:{kw}", "usajobs", sources.usajobs, (kw,))
                  for kw in ("quality assurance", "software testing", "test engineer")]
    else:
        missing.append("USAJOBS_KEY + USAJOBS_EMAIL (free — developer.usajobs.gov — adds ~40-80 federal QA roles)")
    if os.environ.get("RAPIDAPI_KEY"):
        tasks += [(f"jsearch:{q}", "jsearch", sources.jsearch, (q,)) for q in AGG_QUERIES]
    else:
        missing.append("RAPIDAPI_KEY (~$30/mo — JSearch — this is where 120-200 CONTRACT roles come from)")
    if os.environ.get("ADZUNA_APP_ID") and os.environ.get("ADZUNA_APP_KEY"):
        tasks += [(f"adzuna:{w}", "adzuna", sources.adzuna, (w,))
                  for w in ("qa automation engineer", "sdet", "test engineer contract")]
    else:
        missing.append("ADZUNA_APP_ID + ADZUNA_APP_KEY (free tier — adds ~40-80 mixed roles)")

    for name, src, fn, args in tasks:
        res = _new_result(name, "agg")
        try:
            recs, err = pull(fn, *args)
            recs = [r for r in recs if isinstance(r, dict)]
            st = ingest_batch(db, recs, now, WANTED_LOOSE)
            _finish(res, recs, err, st)
            (src_ok if res["ok"] and res["raw"] > 0 else src_bad).add(src)
            if not res["ok"]:
                src_bad.add(src)
        except Exception as e:
            db.rollback()
            res["err"] = f"{type(e).__name__}: {str(e)[:100]}"
            src_bad.add(src)
        results.append(res)
    expired = expire_aggregators(db, now, src_ok - src_bad, expire_days)
    if missing:
        print("\n  Not configured — each of these adds real volume:")
        for m in missing:
            print(f"    · {m}")
    return results, expired


def clean_live_board(db):
    """Deactivate sample data, placeholder titles and legacy duplicates.

    Seed rows are only retired once real (non-seed) jobs are live, so a first
    ingest that fails does not leave a dev board empty.
    """
    seeded = 0
    has_real = db.query(Job.fingerprint).filter(Job.active.is_(True), Job.source != "seed").first()
    if has_real:
        seeded = db.query(Job).filter(Job.source == "seed", Job.active.is_(True)).update(
            {"active": False}, synchronize_session=False)
    live = db.query(Job.fingerprint, Job.title, Job.source, Job.source_id,
                    Job.apply_url, Job.company, Job.posted_at) \
        .filter(Job.active.is_(True)).order_by(Job.first_seen.desc()).all()
    bad, seen = [], set()
    placeholders = duplicates = unverifiable = stale = 0
    now = dt.datetime.now(dt.timezone.utc)
    for fp, title, src, sid, url, company, posted in live:
        if PLACEHOLDER_TITLE.match((title or "").strip()) or quality.bad_title(title) \
                or quality.bad_company(company):
            bad.append(fp); placeholders += 1
            continue
        if src != "seed":
            if quality.normalize_apply_url(url) is None:
                bad.append(fp); unverifiable += 1
                continue
            if quality.is_stale(posted, src, now):
                bad.append(fp); stale += 1
                continue
        key = (src, sid)
        if sid and key in seen:
            bad.append(fp); duplicates += 1
        else:
            seen.add(key)
    for i in range(0, len(bad), 500):
        db.query(Job).filter(Job.fingerprint.in_(bad[i:i + 500])).update(
            {"active": False}, synchronize_session=False)
    db.commit()
    return {"seeded": seeded, "placeholders": placeholders, "duplicates": duplicates,
            "bad_url": unverifiable, "stale": stale}


def prune(db, days=45, now=None):
    """Remove jobs not seen for `days`. Rows an application points at are
    deactivated, never deleted (applications.fingerprint is a foreign key and
    the tracker must keep working). Refuses to run if nothing has been seen
    recently, since then ingestion is broken and EVERYTHING looks stale."""
    now = now or dt.datetime.now(dt.timezone.utc)
    if db.query(Job.fingerprint).filter(Job.last_seen >= now - dt.timedelta(days=3)).first() is None:
        return {"deleted": 0, "deactivated": 0, "skipped": "no job seen in the last 3 days; ingest looks broken"}
    cutoff = now - dt.timedelta(days=days)
    referenced = select(Application.fingerprint).where(Application.fingerprint.isnot(None))
    old = db.query(Job).filter(Job.last_seen < cutoff)
    deleted = old.filter(~Job.fingerprint.in_(referenced)) \
        .delete(synchronize_session=False)
    deactivated = db.query(Job).filter(Job.last_seen < cutoff, Job.active.is_(True)) \
        .update({"active": False}, synchronize_session=False)
    db.commit()
    return {"deleted": deleted, "deactivated": deactivated, "skipped": ""}


def report(db):
    now = dt.datetime.now(dt.timezone.utc)
    live = db.query(Job).filter(Job.active.is_(True))
    total = live.count()
    ft = live.filter(Job.employment == "fulltime").count()
    ct = live.filter(Job.employment == "contract").count()
    unk = live.filter(Job.employment == "unknown").count()
    agency = live.filter(Job.company_type == "staffing").count()
    day = now - dt.timedelta(days=1)
    fresh = live.filter(Job.first_seen >= day).count()
    week = live.filter(Job.first_seen >= now - dt.timedelta(days=7)).count()
    no_skills = sum(1 for (s,) in live.with_entities(Job.required_skills).all() if not s)

    print("\n" + "=" * 58)
    print("  LIVE BOARD")
    print("=" * 58)
    print(f"  total live          {total:>6,}")
    print(f"  full-time           {ft:>6,}   target {TARGET_FULLTIME}   {'OK' if ft >= TARGET_FULLTIME else 'SHORT by ' + str(TARGET_FULLTIME - ft)}")
    print(f"  contract            {ct:>6,}   target {TARGET_CONTRACT}   {'OK' if ct >= TARGET_CONTRACT else 'SHORT by ' + str(TARGET_CONTRACT - ct)}")
    print(f"  type unclear        {unk:>6,}")
    print(f"  via staffing agency {agency:>6,}")
    print(f"  added last 24h      {fresh:>6,}   last 7d {week:,}   (autopilot matches on these)")
    print(f"  with skills tagged  {total - no_skills:>6,}   without {no_skills:,}")
    by_src = db.query(Job.source, text("count(*)")).filter(Job.active.is_(True)) \
        .group_by(Job.source).order_by(text("count(*) desc")).all()
    if by_src:
        print("  by source           " + "  ".join(f"{s or '?'} {n}" for s, n in by_src))

    if ct < TARGET_CONTRACT:
        print("\n  Contract roles are short. They come almost entirely from the")
        print("  aggregator leg — agencies post to Dice and job boards, not to")
        print("  Greenhouse. Check RAPIDAPI_KEY and ADZUNA_APP_ID are set.")
    if ft < TARGET_FULLTIME:
        print("\n  Full-time is short. Add more ATS boards to companies.yaml —")
        print("  every 100 boards adds roughly 30-60 live QA roles.")
    print()


def summarize(results, expired, closed_by_board, cleaned, t0, mode, deferred_note=""):
    tot = _zero()
    for r in results:
        for k in tot:
            tot[k] += r.get(k, 0)
    attempted = [r for r in results if not r["deferred"]]
    ok = [r for r in attempted if r["ok"]]
    failed = [r for r in attempted if not r["ok"]]
    deferred = [r for r in results if r["deferred"]]
    status = "failed" if attempted and not ok else ("degraded" if failed else "ok")
    line = (f"INGEST SUMMARY status={status} mode={mode} new={tot['new']} relisted={tot['relisted']} "
            f"seen={tot['seen']} filtered={tot['skipped']} rejected={tot['rejected']} bad_rows={tot['bad']} "
            f"deactivated={closed_by_board + expired} sources_ok={len(ok)}/{len(attempted)} "
            f"failed={len(failed)} deferred={len(deferred)} duration={time.time()-t0:.0f}s")
    return line, status, failed, deferred


def _step_summary(line, failed, deferred):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"### Job ingest\n\n`{line}`\n\n")
            if failed:
                fh.write("Failed sources (first 15):\n\n")
                for r in failed[:15]:
                    fh.write(f"- `{r['name']}` — {r['err']}\n")
            if deferred:
                fh.write(f"\n{len(deferred)} sources deferred (time budget); they rotate next run.\n")
    except OSError:
        pass


def _verify_pass(db, a, t0):
    """Bounded link check after ingest. Time budget: INGEST_VERIFY_SECONDS
    (default 60), and never past the run's own --max-seconds."""
    empty = {"checked": 0, "ok": 0, "dead": 0, "blocked": 0, "unreachable": 0, "error": 0,
             "skipped": 0, "deactivated": 0}
    if not getattr(a, "verify", True) or os.environ.get("INGEST_VERIFY", "1") == "0":
        return empty
    budget = int(os.environ.get("INGEST_VERIFY_SECONDS", "60") or 60)
    if a.max_seconds:
        budget = min(budget, int(a.max_seconds - (time.time() - t0) - 15))
    try:
        return verify.verify_links(db, budget_s=budget)
    except Exception as e:                       # verification must never fail the ingest
        db.rollback()
        print(f"  ! link verification failed: {type(e).__name__}: {str(e)[:100]}", file=sys.stderr)
        return empty


def cycle(db, a, ats=True, agg=True):
    """One ingest pass. Returns (exit_code)."""
    now = dt.datetime.now(dt.timezone.utc)
    t0 = time.time()
    mono0 = time.monotonic()
    max_s = a.max_seconds
    # Leave 90s of margin after the last fetch for sweeps, report, prune, exit.
    sources.set_deadline(mono0 + max(30, max_s - 90) if max_s else None)
    results, expired = [], 0
    try:
        if agg:
            print("[agg] aggregators…")
            r, expired = run_aggregators(db, now, a.agg_expire_days)
            results += r
        if ats:
            boards = load_boards()
            print(f"[ats] {len(boards)} boards…")
            results += run_ats(db, now, boards, a.workers)
    finally:
        sources.set_deadline(None)
    closed = sum(r["swept"] for r in results)
    cleaned = clean_live_board(db)
    checked = _verify_pass(db, a, t0)
    mode = "full" if ats and agg else ("fast" if agg else "ats")
    line, status, failed, deferred = summarize(results, expired, closed, cleaned, t0, mode)
    print(f"  {line}")
    print(f"  cleanup: removed seed {cleaned['seeded']}  placeholders {cleaned['placeholders']}  "
          f"duplicates {cleaned['duplicates']}  bad-url {cleaned['bad_url']}  stale {cleaned['stale']}")
    rej = sum(r.get("rejected", 0) for r in results)
    print(f"  quality gate: rejected {rej} records (bad/placeholder url, title or company, or stale)")
    print(f"  link check: {checked['ok']} verified  {checked['dead']} dead (deactivated)  "
          f"{checked['blocked']} blocked  {checked['unreachable'] + checked['error']} unreachable/error  "
          f"{checked['skipped']} not reached (time budget; next run)")
    for r in [x for x in results if x["note"]][:5]:
        print(f"    ~ {r['name']}: sweep skipped — {r['note']}")
    for r in failed[:10]:
        print(f"    ! {r['name']}: {r['err']}")
    if len(failed) > 10:
        print(f"    … and {len(failed) - 10} more failed sources")
    if deferred:
        print(f"    … {len(deferred)} sources not reached before --max-seconds; they rotate next run")
    _step_summary(line, failed, deferred)
    return 1 if status == "failed" else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="careerpilot job ingest (see module docstring)")
    ap.add_argument("--once", action="store_true", help="one full pass: aggregators + ATS boards")
    ap.add_argument("--loop", action="store_true", help="continuous (local use)")
    ap.add_argument("--fast", action="store_true", help="aggregators only")
    ap.add_argument("--report", action="store_true", help="print board stats and exit")
    ap.add_argument("--prune", action="store_true", help="drop jobs unseen for --prune-days")
    ap.add_argument("--prune-days", type=int, default=45)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--no-verify", dest="verify", action="store_false",
                    help="skip the post-ingest apply-link check")
    ap.add_argument("--max-seconds", type=int,
                    default=1000 if os.environ.get("GITHUB_ACTIONS") else 0,
                    help="time budget for fetching; 0 = unlimited (default 1000 on GitHub Actions)")
    ap.add_argument("--agg-expire-days", type=int, default=21,
                    help="age out aggregator jobs unseen this long (only after a clean fetch)")
    a = ap.parse_args(argv)

    try:
        init_db()
        db = SessionLocal()
        db.execute(text("SELECT 1"))
    except Exception as e:
        print(f"FATAL: database unreachable or schema init failed: {type(e).__name__}: {str(e)[:200]}",
              file=sys.stderr)
        return 2

    if a.report:
        report(db); return 0

    code = 0
    try:
        if a.fast:
            code = cycle(db, a, ats=False, agg=True)
        elif a.once:
            code = cycle(db, a)
        elif a.loop:
            print("Continuous mode. Aggregators every 10 min, ATS sweep every 2 hours.")
            last_ats = 0
            while True:
                do_ats = time.time() - last_ats > 2 * 3600
                try:
                    cycle(db, a, ats=do_ats, agg=True)
                    if do_ats:
                        last_ats = time.time()
                        report(db)
                except Exception as e:
                    db.rollback()
                    print(f"  ! cycle failed: {type(e).__name__}: {e}")
                time.sleep(600)
        elif not a.prune:
            ap.print_help(); return 0
        if a.fast or a.once:
            report(db)
        if a.prune:
            p = prune(db, a.prune_days)
            print(f"PRUNE days={a.prune_days} deleted={p['deleted']} deactivated={p['deactivated']}"
                  + (f" skipped: {p['skipped']}" if p["skipped"] else ""))
    except Exception as e:
        db.rollback()
        print(f"FATAL: {type(e).__name__}: {str(e)[:300]}", file=sys.stderr)
        return 2
    finally:
        db.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
