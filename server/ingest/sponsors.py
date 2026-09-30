# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""H-1B sponsor directory + ATS board discovery (public data only).

    python ingest/sponsors.py load                      # find + load latest USCIS file
    python ingest/sponsors.py load --csv file.csv       # or a local/remote file
    python ingest/sponsors.py discover --top 600        # find public ATS boards for top sponsors

`load`     reads the public USCIS H-1B Employer Data Hub CSV and stores each
           employer brand's approvals for its latest fiscal year (h1b_sponsors).
`discover` probes Greenhouse / Lever / Ashby for each top sponsor's own board and
           records live ones (discovered_boards); the normal ingest then pulls
           their QA/SDET jobs through the same verified pipeline as companies.yaml.

Identity rule: a board is accepted only when the slug is the employer's own name
(full name, hyphenated, or single-word brand); Greenhouse boards are also checked
against the board's published name. Probed-but-missing employers are remembered so
reruns are cheap. USCIS figures are filing history, not current policy.
"""
import argparse, csv, datetime as dt, io, os, re, sys
from concurrent.futures import ThreadPoolExecutor

try:
    from ingest import sources
except ImportError:                                   # run as a script
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from ingest import sources
from api.sponsors import brand_key, clean_name

ARCHIVE_PAGE = "https://www.uscis.gov/archive/h-1b-employer-data-hub-files"
DISCOVER_ATS = ("greenhouse", "lever", "ashby")


# ── loading the USCIS file ──────────────────────────────────────────
def find_csv_url(page=ARCHIVE_PAGE):
    """Newest data-hub CSV linked from the USCIS archive page (by year in the link)."""
    r = sources._get(page)
    r.raise_for_status()
    links = set(re.findall(r'href="([^"]+\.csv[^"]*)"', r.text, re.I))
    best = None
    for u in links:
        m = re.findall(r"(20\d\d)", u)
        if m and "h1b" in u.lower().replace("-", ""):
            y = max(int(x) for x in m)
            if best is None or y > best[0]:
                best = (y, u)
    if not best:
        raise RuntimeError("no H-1B data hub CSV link found on the USCIS page — pass --csv URL_OR_PATH")
    u = best[1]
    return u if u.startswith("http") else "https://www.uscis.gov" + u


def read_text(src):
    if re.match(r"^https?://", src):
        r = sources._get(src)
        r.raise_for_status()
        raw = r.content
    else:
        raw = open(src, "rb").read()
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeError, ValueError):
            continue
    return raw.decode("latin-1", "replace")


def _num(v):
    try:
        return int(str(v).replace(",", "").strip() or 0)
    except ValueError:
        return 0


def parse_rows(text):
    """Yield (fy, name, city, state, approvals) from the hub CSV. Columns are found
    by header text so a renamed/reordered column doesn't silently corrupt data."""
    first = text.split("\n", 1)[0]
    delim = "\t" if first.count("\t") > first.count(",") else ","
    rd = csv.reader(io.StringIO(text), delimiter=delim)
    head = [h.strip().lower() for h in next(rd)]

    def col(*needles):
        for i, h in enumerate(head):
            if all(n in h for n in needles):
                return i
        return None
    i_fy, i_nm = col("fiscal"), col("employer")
    i_city, i_st = col("city"), col("state")
    i_ia, i_ca = col("initial", "approval"), col("continuing", "approval")
    if None in (i_fy, i_nm) or (i_ia is None and i_ca is None):
        raise RuntimeError(f"unrecognised USCIS columns: {head}")
    for row in rd:
        if len(row) <= max(i for i in (i_fy, i_nm, i_ia or 0, i_ca or 0)):
            continue
        fy = _num(row[i_fy])
        name = row[i_nm].strip()
        if not fy or not name:
            continue
        ap = (_num(row[i_ia]) if i_ia is not None else 0) + (_num(row[i_ca]) if i_ca is not None else 0)
        yield (fy, name, row[i_city].strip() if i_city is not None else "",
               row[i_st].strip() if i_st is not None else "", ap)


def aggregate(rows):
    """{brand_key: {name, fy, approvals, city, state}} at each brand's latest FY,
    summing every filing entity that maps to the brand."""
    by = {}
    for fy, name, city, st, ap in rows:
        k = brand_key(name)
        if not k:
            continue
        e = by.setdefault(k, {}).setdefault(fy, {"approvals": 0, "top": (-1, name, city, st)})
        e["approvals"] += ap
        if ap > e["top"][0]:
            e["top"] = (ap, name, city, st)
    out = {}
    for k, years in by.items():
        fy = max(years)
        e = years[fy]
        _, name, city, st = e["top"]
        out[k] = {"name": name, "fy": fy, "approvals": e["approvals"], "city": city, "state": st}
    return out


def store_sponsors(db, agg):
    from api.models import H1BSponsor
    existing = {r.brand_key: r for r in db.query(H1BSponsor).all()}
    n = 0
    for k, v in agg.items():
        if v["approvals"] <= 0:
            continue
        row = existing.get(k)
        if row:
            row.name, row.approvals, row.fy, row.city, row.state = \
                v["name"], v["approvals"], v["fy"], v["city"], v["state"]
        else:
            db.add(H1BSponsor(brand_key=k, name=v["name"], approvals=v["approvals"], fy=v["fy"],
                              city=v["city"], state=v["state"]))
        n += 1
    db.commit()
    return n


# ── discovering boards ──────────────────────────────────────────────
def slug_candidates(name):
    """Conservative slugs for an employer's own board (see module docstring)."""
    toks = clean_name(name).split()
    if not toks:
        return []
    c = ["".join(toks), "-".join(toks)]
    if len(toks) == 1 or (len(toks[0]) >= 6 and len(toks) <= 2):
        c.append(toks[0])
    seen, out = set(), []
    for s in c:
        if len(s) >= 3 and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _gh_name_ok(slug, name):
    try:
        r = sources._get(f"https://boards-api.greenhouse.io/v1/boards/{slug}")
        if r.status_code != 200:
            return False
        bn = (r.json() or {}).get("name", "")
    except Exception:
        return False
    a, b = brand_key(bn), brand_key(name)
    return bool(a) and (a == b or a.startswith(b + " ") or b.startswith(a + " "))


def probe_board(name):
    """(ats, slug, job_count) for the first own board found, else None."""
    for ats in DISCOVER_ATS:
        for slug in slug_candidates(name):
            try:
                recs = list(sources.ATS[ats](slug, name))
            except Exception:
                continue                               # 404 / network: try next candidate
            if not recs:
                continue
            if ats == "greenhouse" and not _gh_name_ok(slug, name):
                continue
            return ats, slug, len(recs)
    return None


def discover(db, top=600, workers=8, recheck_days=30, probe=probe_board):
    from api.models import H1BSponsor, DiscoveredBoard
    now = dt.datetime.now(dt.timezone.utc)
    done = {r.brand_key: r for r in db.query(DiscoveredBoard).all()}
    cutoff = now - dt.timedelta(days=recheck_days)
    todo = []
    for s in db.query(H1BSponsor).order_by(H1BSponsor.approvals.desc()).limit(top).all():
        d = done.get(s.brand_key)
        ca = d.checked_at if d else None
        if ca is not None and ca.tzinfo is None:
            ca = ca.replace(tzinfo=dt.timezone.utc)
        if d and ca and ca > cutoff:
            continue
        todo.append(s)
    found = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(lambda s: (s, probe(s.name)), todo))
    for s, hit in results:
        db.query(DiscoveredBoard).filter(DiscoveredBoard.brand_key == s.brand_key).delete()
        if hit:
            ats, slug, n = hit
            db.add(DiscoveredBoard(brand_key=s.brand_key, ats=ats, slug=slug, jobs=n,
                                   label=clean_name(s.name).title(), approvals=s.approvals, checked_at=now))
            found += 1
        else:
            db.add(DiscoveredBoard(brand_key=s.brand_key, ats="none", slug="", approvals=s.approvals,
                                   checked_at=now))
    db.commit()
    return {"probed": len(todo), "found": found, "skipped_recent": min(top, db.query(H1BSponsor).count()) - len(todo)}


def discovered_boards(db):
    """Live discovered boards as (ats, slug, label) for the ingest."""
    from api.models import DiscoveredBoard
    try:
        return [(r.ats, r.slug, r.label or r.slug) for r in
                db.query(DiscoveredBoard).filter(DiscoveredBoard.ats != "none").all()
                if r.ats in sources.ATS]
    except Exception:
        db.rollback()
        return []


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("load")
    l.add_argument("--csv", help="URL or path of a USCIS data-hub CSV (default: newest on the archive page)")
    d = sub.add_parser("discover")
    d.add_argument("--top", type=int, default=600)
    d.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(argv)
    from api.db import init_db, SessionLocal
    init_db()
    db = SessionLocal()
    try:
        if a.cmd == "load":
            src = a.csv or find_csv_url()
            print(f"loading {src}")
            agg = aggregate(parse_rows(read_text(src)))
            print(f"stored {store_sponsors(db, agg)} employer brands")
        else:
            print(discover(db, a.top, a.workers))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
