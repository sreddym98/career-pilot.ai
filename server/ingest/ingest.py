# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""
Job ingestion pipeline.

Two legs:
  LEG A - ATS public endpoints (free, clean, direct employers)
  LEG B - Aggregator API (paid, broad, catches staffing agencies)

Run daily via cron. Target: 100+ new/relisted jobs per day.

    python ingest.py --init          # create db
    python ingest.py --run           # daily pull
    python ingest.py --report        # what's new today
"""

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

DB = os.environ.get("JOBS_DB", "jobs.db")
UA = {"User-Agent": "jobfeed/1.0 (+contact@yourdomain.com)"}
TIMEOUT = 20


# ─────────────────────────────────────────────────────────────
# SCHEMA
# ─────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    fingerprint   TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    source_id     TEXT,
    company       TEXT NOT NULL,
    company_type  TEXT,              -- 'employer' | 'staffing'
    title         TEXT NOT NULL,
    location      TEXT,
    remote        INTEGER DEFAULT 0,
    employment    TEXT,              -- 'fulltime' | 'contract' | 'unknown'
    description   TEXT,
    url           TEXT,
    posted_at     TEXT,
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    seen_count    INTEGER DEFAULT 1,
    relisted      INTEGER DEFAULT 0,
    active        INTEGER DEFAULT 1,
    role_family   TEXT,
    classified_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_first_seen ON jobs(first_seen);
CREATE INDEX IF NOT EXISTS idx_family     ON jobs(role_family);
CREATE INDEX IF NOT EXISTS idx_active     ON jobs(active);
CREATE INDEX IF NOT EXISTS idx_company    ON jobs(company);

CREATE TABLE IF NOT EXISTS sources (
    slug        TEXT PRIMARY KEY,
    ats         TEXT NOT NULL,       -- greenhouse | lever | ashby
    label       TEXT,
    kind        TEXT DEFAULT 'employer',
    last_ok     TEXT,
    fail_count  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS runs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    started   TEXT,
    finished  TEXT,
    new_jobs  INTEGER DEFAULT 0,
    relisted  INTEGER DEFAULT 0,
    seen      INTEGER DEFAULT 0,
    errors    INTEGER DEFAULT 0
);
"""


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def now():
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────
# FINGERPRINTING  (dedup across sources)
# ─────────────────────────────────────────────────────────────

STOP = {"senior", "sr", "junior", "jr", "lead", "staff", "principal", "i", "ii", "iii",
        "the", "a", "an", "and", "of", "for", "with", "remote", "hybrid", "onsite"}


def norm(s):
    if not s:
        return ""
    s = s.lower()
    s = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in s)
    toks = [t for t in s.split() if t not in STOP]
    return " ".join(sorted(toks))


STATES = {"al","ak","az","ar","ca","co","ct","de","fl","ga","hi","id","il","in","ia","ks",
          "ky","la","me","md","ma","mi","mn","ms","mo","mt","ne","nv","nh","nj","nm","ny",
          "nc","nd","oh","ok","or","pa","ri","sc","sd","tn","tx","ut","vt","va","wa","wv",
          "wi","wy","dc"}


def norm_location(s):
    """
    'O Fallon, MO' and 'OFallon MO' and "O'Fallon, Missouri" must collapse.
    Strategy: strip ALL non-alnum (not to spaces), then split state off the tail.
    """
    if not s:
        return ""
    s = s.lower()
    if "remote" in s:
        return "remote"
    parts = [p.strip() for p in s.replace("|", ",").split(",") if p.strip()]
    state = ""
    if parts:
        tail = "".join(ch for ch in parts[-1] if ch.isalnum())
        if tail in STATES:
            state = tail
            parts = parts[:-1]
    city = "".join(ch for ch in " ".join(parts) if ch.isalnum())
    return f"{city[:24]}{state}"


def fingerprint(company, title, location):
    """Same role posted to 4 boards collapses to one row."""
    key = f"{norm(company)}|{norm(title)}|{norm_location(location)}"
    return hashlib.sha256(key.encode()).hexdigest()[:20]


def guess_employment(text, explicit=None):
    if explicit:
        e = explicit.lower()
        if "contract" in e or "temp" in e or "c2c" in e or "w2" in e:
            return "contract"
        if "full" in e or "permanent" in e:
            return "fulltime"
    t = (text or "").lower()[:3000]
    contract_hits = sum(k in t for k in
                        ["c2c", "corp to corp", "w2 contract", "contract role",
                         "contract position", "months contract", "month contract",
                         "1099", "contract to hire", "long term contract"])
    ft_hits = sum(k in t for k in
                  ["full-time", "full time", "permanent position", "fte", "salaried"])
    if contract_hits > ft_hits:
        return "contract"
    if ft_hits:
        return "fulltime"
    return "unknown"


import re

# Substring markers — appear anywhere in the name
STAFFING_SUBSTR = [
    "staffing", "consulting", "consultancy", "infotech", "recruit", "placement",
    "talent", "resourcing", "manpower", "workforce", "hcl", "outsourc",
    "it services", "technologies", "technology solutions", "software solutions",
    "systems inc", "solutions inc", "global services", "e-solutions", "esolutions",
]

# Structural patterns common to IT staffing shops
STAFFING_PATTERNS = [
    r"\bsource\b",           # Net2Source, iSource, TekSource
    r"net\d",                # Net2Source
    r"\btek\b|tek$",         # Techrakers, Collabtek, Nutek
    r"\bsoft\b|soft$",       # Compunnel Soft, Rangam Soft
    r"\binc\.?$",            # bare "... Inc" with no product brand
    r"\bllc$",
    r"\bgroup$",             # ASCII Group
    r"\bcorp(oration)?$",    # VBeyond Corporation
    r"\bventures?\b",
    r"\bpartners?$",
    r"\bassociates?$",
    r"\bconsultants?$",
    r"\bsolutions?$",
    r"\bsystems?$",
    r"\bservices?$",
]

# Text-level tells — stronger signal than the name
STAFFING_TEXT = [
    "our client", "client is seeking", "on behalf of our client", "end client",
    "implementation partner", "c2c", "corp to corp", "corp-to-corp",
    "w2 only", "no c2c", "submit your resume to", "rate:", "visa status",
    "usc, h1b", "h1b, h4", "only h1", "third party", "prime vendor",
]


def guess_company_type(company, text=""):
    c = (company or "").strip().lower()
    t = (text or "").lower()[:3000]

    # Text signal wins — an agency posting always reveals itself in the body
    hits = sum(k in t for k in STAFFING_TEXT)
    if hits >= 2:
        return "staffing"

    if any(m in c for m in STAFFING_SUBSTR):
        return "staffing"
    if any(re.search(p, c) for p in STAFFING_PATTERNS):
        return "staffing"
    if hits >= 1:
        return "staffing"
    return "employer"


# ─────────────────────────────────────────────────────────────
# LEG A — ATS CONNECTORS (free, public, no auth)
# ─────────────────────────────────────────────────────────────

def fetch_greenhouse(slug):
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        out.append({
            "source": "greenhouse",
            "source_id": str(j.get("id")),
            "title": j.get("title", ""),
            "location": (j.get("location") or {}).get("name", ""),
            "description": j.get("content", "") or "",
            "url": j.get("absolute_url", ""),
            "posted_at": j.get("updated_at"),
        })
    return out


def fetch_lever(slug):
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for j in r.json():
        cat = j.get("categories") or {}
        out.append({
            "source": "lever",
            "source_id": j.get("id"),
            "title": j.get("text", ""),
            "location": cat.get("location", ""),
            "employment_hint": cat.get("commitment", ""),
            "description": j.get("descriptionPlain", "") or j.get("description", "") or "",
            "url": j.get("hostedUrl", ""),
            "posted_at": datetime.fromtimestamp(
                j["createdAt"] / 1000, timezone.utc).isoformat() if j.get("createdAt") else None,
        })
    return out


def fetch_ashby(slug):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        out.append({
            "source": "ashby",
            "source_id": j.get("id"),
            "title": j.get("title", ""),
            "location": j.get("location", ""),
            "employment_hint": j.get("employmentType", ""),
            "description": j.get("descriptionPlain", "") or "",
            "url": j.get("jobUrl", ""),
            "posted_at": j.get("publishedAt"),
            "remote": 1 if j.get("isRemote") else 0,
        })
    return out


ATS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby}


# ─────────────────────────────────────────────────────────────
# LEG B — AGGREGATOR (catches staffing agencies / Dice / boards)
# ─────────────────────────────────────────────────────────────

def fetch_jsearch(query, pages=2, date_posted="today"):
    """
    JSearch via RapidAPI reads Google-for-Jobs — this is the leg that
    surfaces Net2Source / Ampstek / Yochana style staffing postings.
    Set RAPIDAPI_KEY in env. Skips silently if absent.
    """
    key = os.environ.get("RAPIDAPI_KEY")
    if not key:
        return []
    out = []
    for page in range(1, pages + 1):
        r = requests.get(
            "https://jsearch.p.rapidapi.com/search",
            headers={"X-RapidAPI-Key": key, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"},
            params={"query": query, "page": page, "num_pages": 1,
                    "date_posted": date_posted, "country": "us"},
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            break
        for j in r.json().get("data", []):
            loc = ", ".join(filter(None, [j.get("job_city"), j.get("job_state")]))
            out.append({
                "source": "jsearch",
                "source_id": j.get("job_id"),
                "company": j.get("employer_name", ""),
                "title": j.get("job_title", ""),
                "location": loc,
                "remote": 1 if j.get("job_is_remote") else 0,
                "employment_hint": j.get("job_employment_type", ""),
                "description": j.get("job_description", "") or "",
                "url": j.get("job_apply_link", ""),
                "posted_at": j.get("job_posted_at_datetime_utc"),
            })
        time.sleep(1)
    return out


# ─────────────────────────────────────────────────────────────
# UPSERT — this is where new vs relisted is decided
# ─────────────────────────────────────────────────────────────

RELIST_GAP_DAYS = 21


def upsert(conn, rec, company, company_type):
    fp = fingerprint(company, rec["title"], rec.get("location", ""))
    ts = now()
    cur = conn.execute("SELECT * FROM jobs WHERE fingerprint=?", (fp,))
    row = cur.fetchone()

    if row is None:
        conn.execute("""
            INSERT INTO jobs (fingerprint, source, source_id, company, company_type,
                title, location, remote, employment, description, url, posted_at,
                first_seen, last_seen, seen_count, relisted, active)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,0,1)
        """, (fp, rec["source"], rec.get("source_id"), company, company_type,
              rec["title"], rec.get("location", ""), rec.get("remote", 0),
              guess_employment(rec.get("description"), rec.get("employment_hint")),
              rec.get("description", "")[:20000], rec.get("url", ""),
              rec.get("posted_at"), ts, ts))
        return "new"

    # seen before — was it gone long enough to count as a relist?
    last = datetime.fromisoformat(row["last_seen"])
    gap = (datetime.now(timezone.utc) - last).days
    relisted = 1 if (gap >= RELIST_GAP_DAYS or row["active"] == 0) else row["relisted"]
    status = "relisted" if (gap >= RELIST_GAP_DAYS or row["active"] == 0) else "seen"

    conn.execute("""
        UPDATE jobs SET last_seen=?, seen_count=seen_count+1, relisted=?, active=1,
               url=COALESCE(NULLIF(?,''), url)
        WHERE fingerprint=?
    """, (ts, relisted, rec.get("url", ""), fp))
    return status


def mark_stale(conn, days=14):
    """Anything not seen in N days is probably closed. Kills ghost jobs."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cur = conn.execute("UPDATE jobs SET active=0 WHERE last_seen < ? AND active=1", (cutoff,))
    return cur.rowcount


# ─────────────────────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────────────────────

QUERIES = [
    "SDET jobs in USA",
    "QA automation engineer jobs in USA",
    "test automation engineer contract USA",
    "ETL tester jobs in USA",
    "performance test engineer jobs in USA",
]


def run():
    conn = db()
    started = now()
    stats = {"new": 0, "relisted": 0, "seen": 0}
    errors = 0

    # LEG A
    sources = conn.execute("SELECT * FROM sources WHERE fail_count < 5").fetchall()
    print(f"[ats] polling {len(sources)} boards")
    for s in sources:
        try:
            recs = ATS[s["ats"]](s["slug"])
            label = s["label"] or s["slug"]
            for rec in recs:
                ctype = s["kind"] or guess_company_type(label, rec.get("description"))
                stats[upsert(conn, rec, label, ctype)] += 1
            conn.execute("UPDATE sources SET last_ok=?, fail_count=0 WHERE slug=?",
                         (now(), s["slug"]))
        except Exception as e:
            errors += 1
            conn.execute("UPDATE sources SET fail_count=fail_count+1 WHERE slug=?", (s["slug"],))
            print(f"  ! {s['slug']}: {e}", file=sys.stderr)
        time.sleep(0.4)
        conn.commit()

    # LEG B
    if os.environ.get("RAPIDAPI_KEY"):
        print(f"[agg] {len(QUERIES)} queries")
        for q in QUERIES:
            try:
                for rec in fetch_jsearch(q):
                    company = rec.pop("company", "") or "Unknown"
                    stats[upsert(conn, rec, company,
                                 guess_company_type(company, rec.get("description")))] += 1
            except Exception as e:
                errors += 1
                print(f"  ! {q}: {e}", file=sys.stderr)
            conn.commit()
    else:
        print("[agg] skipped — no RAPIDAPI_KEY (this is the staffing-agency leg)")

    closed = mark_stale(conn)
    conn.execute("""INSERT INTO runs (started, finished, new_jobs, relisted, seen, errors)
                    VALUES (?,?,?,?,?,?)""",
                 (started, now(), stats["new"], stats["relisted"], stats["seen"], errors))
    conn.commit()

    print(f"\nnew={stats['new']}  relisted={stats['relisted']}  "
          f"already-seen={stats['seen']}  closed={closed}  errors={errors}")
    if stats["new"] + stats["relisted"] < 100:
        print("→ under 100/day. Add more source slugs, or enable the aggregator leg.")
    conn.close()


def report():
    conn = db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    rows = conn.execute("""
        SELECT company, company_type, title, location, employment, url
        FROM jobs WHERE first_seen > ? AND active=1
        ORDER BY company_type, company LIMIT 200
    """, (cutoff,)).fetchall()
    print(f"{len(rows)} new in last 24h\n")
    for r in rows:
        tag = "AGENCY" if r["company_type"] == "staffing" else "DIRECT"
        print(f"[{tag}] {r['company'][:28]:30} {r['title'][:44]:46} "
              f"{(r['location'] or '')[:20]:22} {r['employment']}")
    conn.close()


def load_companies():
    """Read ingest/companies.yaml. Falls back to a tiny built-in list if
    the file is missing, so a fresh clone still runs."""
    import re as _re, os as _os
    path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "companies.yaml")
    if not _os.path.exists(path):
        return [("stripe", "greenhouse", "Stripe"), ("plaid", "lever", "Plaid"),
                ("ramp", "ashby", "Ramp")]
    out, section = [], None
    for line in open(path, encoding="utf-8"):
        if line.strip().startswith("#") or not line.strip():
            continue
        m = _re.match(r"^(\w+):", line)
        if m and not line.startswith(" "):
            section = m.group(1)
            continue
        m = _re.match(r"^\s*-\s*\{slug:\s*([^,}]+),\s*label:\s*([^}]+)\}", line)
        if m and section in ("greenhouse", "lever", "ashby"):
            out.append((m.group(1).strip(), section, m.group(2).strip()))
    return out


SEED = load_companies()

def init():
    conn = db()
    conn.executescript(SCHEMA)
    for slug, ats, label in SEED:
        conn.execute("INSERT OR IGNORE INTO sources (slug, ats, label) VALUES (?,?,?)",
                     (slug, ats, label))
    conn.commit()
    n = conn.execute("SELECT COUNT(*) c FROM sources").fetchone()["c"]
    print(f"initialized {DB} with {n} sources")
    conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--init", action="store_true")
    p.add_argument("--run", action="store_true")
    p.add_argument("--report", action="store_true")
    a = p.parse_args()
    if a.init:
        init()
    elif a.run:
        run()
    elif a.report:
        report()
    else:
        p.print_help()
