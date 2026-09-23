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
from api.settings import settings
try:
    from dotenv import dotenv_values
except ImportError:
    dotenv_values = lambda *_args, **_kwargs: {}

HERE = os.path.dirname(os.path.abspath(__file__))

# The API loads .env through Pydantic settings, but this runner also supports
# direct execution. Mirror source credentials into the environment so the
# connector functions that read os.environ behave the same way in both modes.
for _name in ("RAPIDAPI_KEY", "USAJOBS_EMAIL", "USAJOBS_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY", "CORESIGNAL_API_KEY"):
    _dotenv = dotenv_values(os.path.join(SERVER_ROOT, ".env"))
    _value = getattr(settings, _name, "") or _dotenv.get(_name, "")
    if _value and not os.environ.get(_name):
        os.environ[_name] = _value

TARGET_FULLTIME = 100
TARGET_CONTRACT = 200

# Every customer needs a complete job market, not a QA-only slice. Source and
# placeholder safeguards below remain in place, but titles are not discarded.
PLACEHOLDER_TITLE = re.compile(
    r"^(test|test job|test job title|test req|quality checker|qa tester entry level)$", re.I)

ROLE_FAMILIES = [
    ("ui", r"\b(sdet|qa|quality assurance|quality engineer|test automation|test engineer|software engineer in test)\b"),
    ("api", r"\b(api|integration|backend test|rest|soap)\b"),
    ("de", r"\b(data engineer|data platform|data warehouse|data architect)\b"),
    ("etl", r"\b(etl|data quality|data pipeline|analytics engineer)\b"),
    ("perf", r"\b(performance|load test|stress test)\b"),
    ("mobqa", r"\b(mobile test|appium|ios test|android test)\b"),
    ("secqa", r"\b(security test|application security|penetration test)\b"),
    ("a11y", r"\b(accessibility|a11y)\b"),
    ("fe", r"\b(frontend|front end|web developer|ui developer)\b"),
    ("be", r"\b(backend|back end|software engineer|software developer|developer)\b"),
    ("sre", r"\b(sre|devops|site reliability|platform engineer)\b"),
    ("cloud", r"\b(cloud engineer|cloud architect)\b"),
    ("ds", r"\b(data scientist|machine learning|ml engineer)\b"),
    ("an", r"\b(data analyst|business intelligence|analytics)\b"),
    ("pm", r"\b(product manager|product owner)\b"),
    ("ux", r"\b(product designer|ux designer|ui designer|graphic designer)\b"),
    ("tpm", r"\b(program manager|project manager|scrum master)\b"),
    ("em", r"\b(engineering manager|software manager)\b"),
    ("qal", r"\b(qa manager|quality manager|test manager|qa lead)\b"),
]


def role_family_for(title):
    normalized = (title or "").lower()
    for family, pattern in ROLE_FAMILIES:
        if re.search(pattern, normalized):
            return family
    return "general"

ALL_ROLE_AGG_QUERIES = [
    "software engineer jobs USA",
    "linkedin software engineer jobs usa",
    "software developer jobs USA",
    "full stack developer jobs USA",
    "frontend developer jobs USA",
    "backend developer jobs USA",
    "data analyst jobs USA",
    "linkedin data analyst jobs usa",
    "product manager jobs USA",
    "linkedin product manager jobs usa",
    "project manager jobs USA",
    "business analyst jobs USA",
    "operations analyst jobs USA",
    "customer success jobs USA",
    "sales engineer jobs USA",
    "account manager jobs USA",
    "support engineer jobs USA",
    "network engineer jobs USA",
    "cloud engineer jobs USA",
    "cybersecurity jobs USA",
    "ux designer jobs USA",
    "data engineer jobs USA",
    "devops engineer jobs USA",
    "hr jobs USA",
    "recruiter jobs USA",
    "finance analyst jobs USA",
    "marketing jobs USA",
    "operations jobs USA",
]

TECH_AGG_QUERIES = [
    "quality engineer jobs USA",
    "qa jobs USA",
    "automation engineer jobs USA",
    "sdet jobs USA",
    "software testing jobs USA",
    "test automation jobs USA",
    "quality assurance jobs USA",
    "software engineer jobs USA",
    "data engineer jobs USA",
    "cybersecurity jobs USA",
    "cloud engineer jobs USA",
]

QA_AGG_QUERIES = [
    "qa jobs USA",
    "linkedin qa jobs usa",
    "quality engineer jobs USA",
    "manual tester jobs USA",
    "automation tester jobs USA",
    "software testing jobs USA",
    "sdet jobs USA",
    "linkedin sdet jobs usa",
    "test automation jobs USA",
    "quality assurance jobs USA",
    "monster qa jobs usa",
    "ziprecruiter automation jobs usa",
    "techfetch quality jobs usa",
    "benchinfo sdet jobs usa",
]

CONTRACT_AGG_QUERIES = [
    "contract jobs USA",
    "corp to corp jobs USA",
    "1099 jobs USA",
    "contractor jobs USA",
    "contract to hire jobs USA",
    "consulting contract jobs USA",
    "C2C developer jobs USA",
    "C2C QA jobs USA",
    "contract QA jobs USA",
    "contract SDET jobs USA",
    "software engineering contract jobs USA",
    "data engineering contract jobs USA",
    "DevOps contract jobs USA",
    "finance technology contract jobs USA",
    "healthcare IT contract jobs USA",
]

AGG_QUERIES = ALL_ROLE_AGG_QUERIES + TECH_AGG_QUERIES + QA_AGG_QUERIES + CONTRACT_AGG_QUERIES

STOP = {"senior", "sr", "jr", "junior", "lead", "staff", "principal", "i", "ii", "iii", "iv",
        "the", "a", "an", "and", "of", "for", "with", "remote", "hybrid", "onsite", "us", "usa"}
STATES = set("al ak az ar ca co ct de fl ga hi id il in ia ks ky la me md ma mi mn ms mo mt ne "
             "nv nh nj nm ny nc nd oh ok or pa ri sc sd tn tx ut vt va wa wv wi wy dc".split())
US_STATE_NAMES = (
    "alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida|georgia|"
    "hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland|massachusetts|"
    "michigan|minnesota|mississippi|missouri|montana|nebraska|nevada|new hampshire|new jersey|"
    "new mexico|new york|north carolina|north dakota|ohio|oklahoma|oregon|pennsylvania|rhode island|"
    "south carolina|south dakota|tennessee|texas|utah|vermont|virginia|washington|west virginia|wisconsin|wyoming"
)
US_JOB = re.compile(r"\b(united states|u\.s\.a?\.?|usa|us[- ]based|remote[- ]?us)\b", re.I)
US_STATE_LOCATION = re.compile(rf",\s*(?:{US_STATE_NAMES})\b", re.I)
US_STATE_ABBREVIATION = re.compile(r",\s*(al|ak|az|ar|ca|co|ct|de|fl|ga|hi|id|il|in|ia|ks|ky|la|me|md|ma|mi|mn|ms|mo|mt|ne|nv|nh|nj|nm|ny|nc|nd|oh|ok|or|pa|ri|sc|sd|tn|tx|ut|vt|va|wa|wv|wi|wy|dc)\b", re.I)


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
DIRECT_EMPLOYER_DENYLIST = {
    "affirm", "stripe", "ro", "brex", "justworks", "faire", "guild", "doordash",
    "uber", "airbnb", "linkedin", "meta", "google", "amazon", "microsoft",
    "apple", "netflix", "paypal", "visa", "adp", "intuit", "slack", "datadog",
    "shopify", "atlassian", "salesforce", "oracle", "ibm", "palantir", "reddit",
    "snap", "x", "nvidia"
}
STAFFING_ALLOWLIST = {
    "net2source", "tekresources", "collabera", "teksystems", "randstad",
    "manpower", "modis", "synergis", "compunnel", "kforce", "cognizant",
    "deloitte", "accenture", "capgemini", "tcs", "infosys", "wipro",
    "virtusa", "hexaware", "pillar", "maven", "c2c", "aon", "insightglobal",
    "toptal", "experis", "diversant", "vgroup", "nityo", "aetec", "apetan",
    "systel", "veterans", "sagitec", "dagger", "scio", "triunity", "gsp", "intersys"
}


def company_type(company, text="", direct_ats=False):
    c = (company or "").lower().strip().replace("&", " and ")
    t = (text or "").lower()[:3000]

    if c in DIRECT_EMPLOYER_DENYLIST:
        return "employer"
    if c in STAFFING_ALLOWLIST:
        return "staffing"
    if direct_ats:
        return "employer"

    name_score = 0
    text_score = 0

    if any(m in c for m in STAFFING_SUB):
        name_score += 1
    if any(re.search(p, c) for p in STAFFING_PAT):
        name_score += 2
    for token in STAFFING_TXT:
        if token in t:
            text_score += 2

    if text_score >= 4 or (name_score >= 2 and text_score >= 2):
        return "staffing"
    if name_score >= 3:
        return "staffing"
    if text_score >= 2 and name_score >= 1:
        return "staffing"
    return "employer"


guess_company_type = company_type


def employment_of(text, hint=None, title=""):
    if hint:
        h = hint.lower()
        if "intern" in h:
            return "internship"
        if "part-time" in h or "part time" in h or "parttime" in h:
            return "parttime"
        if any(k in h for k in ("contract", "temp", "c2c", "w2", "contractor")):
            return "contract"
        if "full" in h or "permanent" in h:
            return "fulltime"
    t = f"{title} {text or ''}".lower()[:5000]
    if re.search(r"\b(intern|internship|co-op)\b", t):
        return "internship"
    if re.search(r"\b(part[- ]?time|parttime)\b", t):
        return "parttime"
    # Enhanced contract detection with more patterns
    contract_patterns = [
        "c2c", "corp to corp", "w2 contract", "contract role", "contract position",
        "months contract", "month contract", "1099", "contract to hire", "long term contract",
        "contract duration", "contractor", "staffing", "temporary", "temp position", "temp role",
        "contingent", "engagement", "assignment", "independent contractor", "sub-contractor",
        "resource", "consulting role", "consulting engagement", "agency", "body shop",
        "labor", "placement", "vendor", "on-site", "on site", "contract assignment",
        "contract employment", "through a staffing", "staffing partner", "placement agency"
    ]
    # These are unambiguous employment signals. A single occurrence is enough;
    # requiring two indicators caused C2C/1099 agency listings to remain unknown.
    explicit_contract_patterns = [
        r"\bc2c\b", r"corp(?:oration)?[- ]to[- ]corp(?:oration)?", r"\b1099\b",
        r"contract[- ]to[- ]hire", r"w2 contract", r"independent contractor",
        r"contract position", r"contract role", r"contractor position",
    ]
    if any(re.search(pattern, t) for pattern in explicit_contract_patterns):
        return "contract"
    c = sum(k in t for k in contract_patterns)
    fulltime_patterns = [
        "full-time", "full time", "permanent position", "permanent role", "fte", "salaried",
        "benefits package", "401k", "equity", "health insurance", "dental", "vision",
        "direct hire", "direct employment", "full-time employee", "w-2 position"
    ]
    f = sum(k in t for k in fulltime_patterns)
    if c > f and c >= 2:  # Require at least 2 contract indicators
        return "contract"
    return "fulltime" if f > 0 else "unknown"


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


def posted_at_of(value):
    """Normalize source timestamps without inventing a posting date."""
    if not value:
        return None
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value / 1000 if value > 1e11 else value, dt.timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        for pattern in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = dt.datetime.strptime(text, pattern)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def is_us_job(rec):
    """Retain only roles whose location explicitly establishes U.S. eligibility."""
    location = rec.get("location", "") or ""
    return bool(US_JOB.search(location) or US_STATE_LOCATION.search(location)
                or US_STATE_ABBREVIATION.search(location))


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
    if not title or not company or PLACEHOLDER_TITLE.match(title) or not is_us_job(rec):
        return None
    desc = rec.get("description") or ""
    published = posted_at_of(rec.get("posted_at"))
    fp = fingerprint(company, title, rec.get("location", ""),
                     rec.get("source", ""), rec.get("source_id", ""))
    pending = getattr(db, "_ingest_fingerprints", set())
    if fp in pending:
        return "seen"
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
        if row.employment in (None, "", "unknown"):
            row.employment = employment_of(desc, rec.get("employment"), title)
        if not row.role_family:
            row.role_family = role_family_for(title)
        if published:
            if row.posted_at is None:
                row.posted_at = published
            elif isinstance(published, dt.datetime) and isinstance(row.posted_at, dt.datetime):
                # Ensure both are timezone-aware for comparison
                pub_aware = published if published.tzinfo else published.replace(tzinfo=dt.timezone.utc)
                row_aware = row.posted_at if row.posted_at.tzinfo else row.posted_at.replace(tzinfo=dt.timezone.utc)
                if pub_aware > row_aware:
                    row.posted_at = published
        return status

    v = parse_visa(desc)
    ct = company_type(company, desc)
    db.add(Job(
        fingerprint=fp, source=rec.get("source", ""), source_id=rec.get("source_id"),
        company=company, company_type=ct, title=title,
        location=rec.get("location", ""),
        work_mode=work_mode(rec.get("location", ""), desc, rec.get("remote")),
        employment=employment_of(desc, rec.get("employment"), title),
        description=desc[:20000], apply_url=rec.get("url", ""),
        visa_usc=v["usc"], visa_gc=v["gc"], visa_h1b=v["h1b"], visa_opt=v["opt"],
        role_family=role_family_for(title), required_skills=[], posted_at=published,
        first_seen=now, last_seen=now, seen_count=1, active=True))
    pending.add(fp)
    db._ingest_fingerprints = pending
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
    non_us = 0
    for row in db.query(Job).filter(Job.active.is_(True)).all():
        if PLACEHOLDER_TITLE.match((row.title or "").strip()):
            row.active = False
            placeholders += 1
        elif not is_us_job({"location": row.location, "description": row.description}):
            row.active = False
            non_us += 1
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
    return {"seeded": seeded, "placeholders": placeholders, "non_us": non_us, "duplicates": duplicates}


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
                r = upsert(db, rec, now)
                if r:
                    stats[r] += 1
            db.commit()
    return stats, errors


CORESIGNAL_STATE_FILE = os.path.join(HERE, ".coresignal_last_run")


def _coresignal_due(min_hours=20):
    """True once per day-ish. run_aggregators() fires every 5 min in --loop
    mode; Coresignal bills per record collected, so it needs its own, much
    slower cadence independent of that loop."""
    try:
        with open(CORESIGNAL_STATE_FILE) as f:
            last = dt.datetime.fromisoformat(f.read().strip())
        return (dt.datetime.now(dt.timezone.utc) - last).total_seconds() >= min_hours * 3600
    except (FileNotFoundError, ValueError):
        return True


def _mark_coresignal_run():
    with open(CORESIGNAL_STATE_FILE, "w") as f:
        f.write(dt.datetime.now(dt.timezone.utc).isoformat())


def run_aggregators(db, now):
    """Free sources run unconditionally. Keyed ones are skipped silently
    if the key is absent, and reported at the end so you know what you're
    missing rather than wondering why contract roles are thin."""
    stats = {"new": 0, "relisted": 0, "seen": 0, "skipped": 0}
    errors = []
    missing = []

    def take(recs):
        for rec in recs:
            if "__error__" in rec:
                errors.append(rec["__error__"]); continue
            r = upsert(db, rec, now)
            if r:
                stats[r] += 1
        db.commit()

    # free, no key
    take(pull(sources.remotive))
    take(pull(sources.remoteok))
    take(pull(sources.arbeitnow))
    take(pull(sources.themuse, 15))
    # free, needs a key you can get in 2 minutes
    if os.environ.get("USAJOBS_KEY"):
        for kw in ("software engineer", "data analyst", "program manager", "cybersecurity", "internship"):
            take(pull(sources.usajobs, kw))
    else:
        missing.append("USAJOBS_KEY (free — developer.usajobs.gov — adds ~40-80 federal QA roles)")

    # metered — this is the contract leg
    if os.environ.get("RAPIDAPI_KEY"):
        for q in AGG_QUERIES:
              take(pull(sources.jsearch, q, pages=2, date_posted="all"))
    else:
        missing.append("RAPIDAPI_KEY (~$30/mo — JSearch — this is where 120-200 CONTRACT roles come from)")

    if os.environ.get("ADZUNA_APP_ID"):
        for w in ("software engineer", "data analyst", "product manager", "internship", "part time jobs"):
            take(pull(sources.adzuna, w))
    else:
        missing.append("ADZUNA_APP_ID + ADZUNA_APP_KEY (free tier — adds ~40-80 mixed roles)")

    # metered — independent global dataset, a second source beyond JSearch/Dice/LinkedIn.
    # run_aggregators() fires every 5 min in --loop mode; Coresignal bills per
    # record collected, so this leg is throttled to once/day regardless of
    # that cadence — without the guard a Mini plan's entire monthly credit
    # budget (2,500) would be spent in under 90 minutes.
    if os.environ.get("CORESIGNAL_API_KEY") and _coresignal_due():
        for q in ("qa engineer", "sdet", "software engineer", "data engineer",
                  "product manager", "devops engineer"):
            take(pull(sources.coresignal, q, max_collect=10))
        _mark_coresignal_run()
    elif not os.environ.get("CORESIGNAL_API_KEY"):
        missing.append("CORESIGNAL_API_KEY (usage-based — coresignal.com — 482M+ deduplicated global postings, a second source beyond JSearch/Dice/LinkedIn)")

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
    qa = live.filter(Job.title.ilike("%qa%") |
                    Job.title.ilike("%quality engineer%") |
                    Job.title.ilike("%sdet%") |
                    Job.title.ilike("%test automation%") |
                    Job.title.ilike("%quality assurance%") |
                    Job.title.ilike("%automation engineer%") |
                    Job.title.ilike("%software testing%")
                    ).count()
    tech = live.filter(
        Job.role_family.in_([
            "ui", "api", "fe", "be", "sre", "cloud", "ds", "de", "etl",
            "perf", "mobqa", "secqa", "a11y", "em", "qal", "pm", "ux", "tpm"
        ])
    ).count()
    day = now - dt.timedelta(days=1)
    fresh = live.filter(Job.first_seen >= day).count()

    print("\n" + "=" * 58)
    print("  LIVE BOARD")
    print("=" * 58)
    print(f"  total live          {total:>6,}")
    print(f"  all-role market     {total:>6,}")
    print(f"  tech / software     {tech:>6,}")
    print(f"  QA / SDET           {qa:>6,}")
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
        db._ingest_fingerprints = set()
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
              f"removed seed {cleaned['seeded']}  placeholders {cleaned['placeholders']}  non-US {cleaned['non_us']}  "
              f"duplicates {cleaned['duplicates']}  errors {len(errs)}  in {time.time()-t0:.0f}s")
        if errs[:5]:
            for x in errs[:5]: print(f"    ! {x}")
        return total

    if a.fast:
        cycle(ats=False, agg=True); report(db); return
    if a.once:
        cycle(); report(db); return
    if a.loop:
        print("Continuous mode. Fast U.S. sources every 5 min, ATS sweep every 2 hours.")
        last_ats = 0
        while True:
            do_ats = time.time() - last_ats > 2 * 3600
            cycle(ats=do_ats, agg=True)
            if do_ats:
                last_ats = time.time()
                report(db)
            time.sleep(scheduler.INTERVAL[scheduler.FAST])
    ap.print_help()


if __name__ == "__main__":
    main()
