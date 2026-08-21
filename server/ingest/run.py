# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""The ingest runner.

    python ingest/run.py --once        one full pass, all sources
    python ingest/run.py --loop        continuous, tier-scheduled (production)
    python ingest/run.py --fast        aggregators only — new contract roles
    python ingest/run.py --report      volume, freshness, gaps vs targets

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

from ingest import sources, scheduler
from ingest.visa_parse import parse_visa
from api.db import SessionLocal, init_db
from api.models import Job

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


def upsert(db, rec, now):
    title = (rec.get("title") or "").strip()
    company = (rec.get("company") or "").strip()
    if not title or not company or PLACEHOLDER_TITLE.match(title):
        return None
    desc = rec.get("description") or ""
    fp = fingerprint(company, title, rec.get("location", ""),
                     rec.get("source", ""), rec.get("source_id", ""))
    row = db.get(Job, fp)

    if row:
        gap = (now - (row.last_seen.replace(tzinfo=dt.timezone.utc)
                      if row.last_seen and row.last_seen.tzinfo is None else row.last_seen)).days \
              if row.last_seen else 0
        status = "relisted" if (gap >= 21 or not row.active) else "seen"
        row.last_seen = now
        row.seen_count = (row.seen_count or 1) + 1
        row.active = True
        if status == "relisted":
            row.relisted = True
        if rec.get("url") and not row.apply_url:
            row.apply_url = rec["url"]
        return status

    v = parse_visa(desc)
    ct = company_type(company, desc)
    db.add(Job(
        fingerprint=fp, source=rec.get("source", ""), source_id=rec.get("source_id"),
        company=company, company_type=ct, title=title,
        location=rec.get("location", ""),
        work_mode=work_mode(rec.get("location", ""), desc, rec.get("remote")),
        employment=employment_of(desc, rec.get("employment")),
        description=desc[:20000], apply_url=rec.get("url", ""),
        visa_usc=v["usc"], visa_gc=v["gc"], visa_h1b=v["h1b"], visa_opt=v["opt"],
        required_skills=[], posted_at=None,
        first_seen=now, last_seen=now, seen_count=1, active=True))
    return "new"


def clean_live_board(db):
    """Deactivate sample data and exact duplicate source records.

    The API board must contain only postings from live connectors. A seed row
    is useful during first-run development but should never compete with a
    verified employer link after the first ingestion succeeds.
    """
    seeded = db.query(Job).filter(Job.source == "seed", Job.active.is_(True)).update(
        {"active": False}, synchronize_session=False)
    placeholders = 0
    for row in db.query(Job).filter(Job.active.is_(True)).all():
        if PLACEHOLDER_TITLE.match((row.title or "").strip()):
            row.active = False
            placeholders += 1
    duplicates = 0
    seen = set()
    rows = db.query(Job).filter(Job.active.is_(True)).order_by(Job.first_seen.desc()).all()
    for row in rows:
        key = (row.source, row.source_id)
        if not row.source_id or key not in seen:
            seen.add(key)
            continue
        row.active = False
        duplicates += 1
    db.commit()
    return {"seeded": seeded, "placeholders": placeholders, "duplicates": duplicates}


def pull(fn, *a, **kw):
    try:
        return list(fn(*a, **kw))
    except Exception as e:
        return [{"__error__": f"{type(e).__name__}: {str(e)[:80]}"}]


def run_ats(db, now, boards, workers=10):
    stats = {"new": 0, "relisted": 0, "seen": 0, "skipped": 0}
    errors = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(pull, sources.ATS[ats], slug, label): (ats, slug, label)
                for ats, slug, label in boards}
        for f in as_completed(futs):
            ats, slug, label = futs[f]
            for rec in f.result():
                if "__error__" in rec:
                    errors.append(f"{ats}/{slug}: {rec['__error__']}")
                    continue
                if not WANTED.search(rec.get("title", "")):
                    stats["skipped"] += 1
                    continue
                r = upsert(db, rec, now)
                if r:
                    stats[r] += 1
            db.commit()
    return stats, errors


def run_aggregators(db, now):
    """Free sources run unconditionally. Keyed ones are skipped silently
    if the key is absent, and reported at the end so you know what you're
    missing rather than wondering why contract roles are thin."""
    stats = {"new": 0, "relisted": 0, "seen": 0, "skipped": 0}
    errors = []
    missing = []

    def take(recs, loose=True):
        pat = WANTED_LOOSE if loose else WANTED
        for rec in recs:
            if "__error__" in rec:
                errors.append(rec["__error__"]); continue
            if not pat.search(rec.get("title", "")):
                stats["skipped"] += 1; continue
            r = upsert(db, rec, now)
            if r:
                stats[r] += 1
        db.commit()

    # free, no key
    take(pull(sources.remotive, "qa"))
    take(pull(sources.remotive, "test"))
    take(pull(sources.remoteok))
    take(pull(sources.arbeitnow))
    # free, needs a key you can get in 2 minutes
    if os.environ.get("USAJOBS_KEY"):
        for kw in ("quality assurance", "software testing", "test engineer"):
            take(pull(sources.usajobs, kw))
    else:
        missing.append("USAJOBS_KEY (free — developer.usajobs.gov — adds ~40-80 federal QA roles)")

    # metered — this is the contract leg
    if os.environ.get("RAPIDAPI_KEY"):
        for q in AGG_QUERIES:
            take(pull(sources.jsearch, q))
    else:
        missing.append("RAPIDAPI_KEY (~$30/mo — JSearch — this is where 120-200 CONTRACT roles come from)")

    if os.environ.get("ADZUNA_APP_ID"):
        for w in ("qa automation engineer", "sdet", "test engineer contract"):
            take(pull(sources.adzuna, w))
    else:
        missing.append("ADZUNA_APP_ID + ADZUNA_APP_KEY (free tier — adds ~40-80 mixed roles)")

    if missing:
        print("\n  Not configured — each of these adds real volume:")
        for m in missing:
            print(f"    · {m}")
    return stats, errors


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

    print("\n" + "=" * 58)
    print("  LIVE BOARD")
    print("=" * 58)
    print(f"  total live          {total:>6,}")
    print(f"  full-time           {ft:>6,}   target {TARGET_FULLTIME}   {'OK' if ft >= TARGET_FULLTIME else 'SHORT by ' + str(TARGET_FULLTIME - ft)}")
    print(f"  contract            {ct:>6,}   target {TARGET_CONTRACT}   {'OK' if ct >= TARGET_CONTRACT else 'SHORT by ' + str(TARGET_CONTRACT - ct)}")
    print(f"  type unclear        {unk:>6,}")
    print(f"  via staffing agency {agency:>6,}")
    print(f"  added last 24h      {fresh:>6,}")

    if ct < TARGET_CONTRACT:
        print("\n  Contract roles are short. They come almost entirely from the")
        print("  aggregator leg — agencies post to Dice and job boards, not to")
        print("  Greenhouse. Check RAPIDAPI_KEY and ADZUNA_APP_ID are set.")
    if ft < TARGET_FULLTIME:
        print("\n  Full-time is short. Add more ATS boards to companies.yaml —")
        print("  every 100 boards adds roughly 30-60 live QA roles.")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--fast", action="store_true", help="aggregators only")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--workers", type=int, default=10)
    a = ap.parse_args()

    init_db()
    db = SessionLocal()

    if a.report:
        report(db); return

    def cycle(ats=True, agg=True):
        now = dt.datetime.now(dt.timezone.utc)
        t0 = time.time()
        total = {"new": 0, "relisted": 0, "seen": 0, "skipped": 0}
        errs = []
        if ats:
            boards = load_boards()
            print(f"[ats] {len(boards)} boards…")
            s, e = run_ats(db, now, boards, a.workers)
            for k in total: total[k] += s[k]
            errs += e
        if agg:
            print("[agg] aggregators…")
            s, e = run_aggregators(db, now)
            for k in total: total[k] += s[k]
            errs += e
        cutoff = now - dt.timedelta(days=10)
        closed = db.query(Job).filter(Job.last_seen < cutoff, Job.active.is_(True))\
            .update({"active": False}, synchronize_session=False)
        db.commit()
        cleaned = clean_live_board(db)
        print(f"  new {total['new']}  relisted {total['relisted']}  seen {total['seen']}  "
              f"filtered-out {total['skipped']}  closed {closed}  "
              f"removed seed {cleaned['seeded']}  placeholders {cleaned['placeholders']}  "
              f"duplicates {cleaned['duplicates']}  errors {len(errs)}  in {time.time()-t0:.0f}s")
        if errs[:5]:
            for x in errs[:5]: print(f"    ! {x}")
        return total

    if a.fast:
        cycle(ats=False, agg=True); report(db); return
    if a.once:
        cycle(); report(db); return
    if a.loop:
        print("Continuous mode. Aggregators every 10 min, ATS sweep every 2 hours.")
        last_ats = 0
        while True:
            do_ats = time.time() - last_ats > 2 * 3600
            cycle(ats=do_ats, agg=True)
            if do_ats:
                last_ats = time.time()
                report(db)
            time.sleep(600)
    ap.print_help()


if __name__ == "__main__":
    main()
