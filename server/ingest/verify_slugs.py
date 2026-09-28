# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Probe every slug in companies.yaml and report what's actually live.

    python ingest/verify_slugs.py            # report only
    python ingest/verify_slugs.py --fix      # move dead slugs to `retired`
    python ingest/verify_slugs.py --qa       # count QA/SDET roles specifically

Why this exists: company ATS slugs go stale. Firms migrate vendors, get
acquired, or rename their board. A curated list is a starting point, not
a source of truth — this makes it true.
"""
import argparse, json, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

import os
try:
    import requests
except ImportError:
    sys.exit("pip install requests")
try:
    import sources                       # run as a script from server/ or ingest/
except ImportError:
    from ingest import sources

HERE = os.path.dirname(os.path.abspath(__file__))
YAML = os.path.join(HERE, "companies.yaml")

# Probe with the SAME connectors the ingest uses, so "live" means "ingestable".
ENDPOINTS = {k: None for k in sources.ATS}

QA_WORDS = re.compile(
    r"\b(sdet|qa|quality engineer|test engineer|automation engineer|"
    r"quality assurance|test automation|software engineer in test|"
    r"qe\b|quality analyst|performance engineer|test architect)\b", re.I)


def load():
    """Tiny YAML reader — this file only ever uses the one shape, so a
    dependency on PyYAML isn't worth it."""
    data, section = {}, None
    for line in open(YAML, encoding="utf-8"):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"^(\w+):\s*(\[\])?$", line.rstrip())
        if m and not line.startswith(" "):
            section = m.group(1)
            data[section] = []
            continue
        m = re.match(r"^\s*-\s*\{slug:\s*([^,}]+),\s*label:\s*([^}]+)\}", line)
        if m and section:
            data[section].append({"slug": m.group(1).strip(),
                                  "label": m.group(2).strip()})
    return data


def probe(ats, slug):
    """ok=False + dead=True only for a definite 404. Timeouts, 429s and 5xx are
    'unverified' (dead=False) so a network blip never retires a good board."""
    try:
        recs = list(sources.ATS[ats](slug, slug))
    except requests.HTTPError as e:
        code = getattr(e.response, "status_code", None)
        return {"ok": False, "dead": code in (404, 410), "n": 0, "qa": 0,
                "why": "404 — slug not found" if code in (404, 410) else f"HTTP {code}"}
    except Exception as e:
        return {"ok": False, "dead": False, "n": 0, "qa": 0, "why": type(e).__name__}
    titles = [r.get("title", "") for r in recs]
    qa = sum(1 for t in titles if QA_WORDS.search(t))
    return {"ok": True, "dead": False, "n": len(recs), "qa": qa, "why": "",
            "sample": [t for t in titles if QA_WORDS.search(t)][:3]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="move dead slugs to `retired`")
    ap.add_argument("--qa", action="store_true", help="show QA/SDET titles found")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    data = load()
    tasks = [(ats, c) for ats in ENDPOINTS for c in data.get(ats, [])]
    print(f"Probing {len(tasks)} boards across {len(ENDPOINTS)} ATS vendors…\n")

    live, dead, unverified, t0 = [], [], [], time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(probe, ats, c["slug"]): (ats, c) for ats, c in tasks}
        done = 0
        for f in as_completed(futs):
            ats, c = futs[f]
            r = f.result()
            done += 1
            if r["ok"]:
                live.append((ats, c, r))
                mark = "✓" if r["n"] else "○"
                extra = f"  {r['qa']} QA" if r["qa"] else ""
                print(f"  {mark} {c['label'][:26]:28} {ats:11} {r['n']:4} jobs{extra}")
                if a.qa and r.get("sample"):
                    for t in r["sample"]:
                        print(f"        · {t[:70]}")
            elif r["dead"]:
                dead.append((ats, c, r))
                print(f"  ✗ {c['label'][:26]:28} {ats:11} {r['why']}")
            else:
                unverified.append((ats, c, r))
                print(f"  ? {c['label'][:26]:28} {ats:11} {r['why']} (not retired)")
            if done % 50 == 0:
                print(f"    … {done}/{len(tasks)}")

    total_jobs = sum(r["n"] for _, _, r in live)
    total_qa = sum(r["qa"] for _, _, r in live)
    empty = sum(1 for _, _, r in live if r["n"] == 0)

    print("\n" + "=" * 62)
    print(f"  live boards      {len(live)} / {len(tasks)}  ({len(live)/max(1,len(tasks))*100:.0f}%)")
    print(f"  dead slugs       {len(dead)}")
    print(f"  unverified       {len(unverified)}   (timeouts / rate limits — left alone)")
    print(f"  live but empty   {empty}   (real board, nothing posted right now)")
    print(f"  total jobs       {total_jobs:,}")
    print(f"  QA / SDET roles  {total_qa:,}")
    print(f"  elapsed          {time.time()-t0:.0f}s")

    # Boards refresh roughly monthly; ~1/30th of the pool turns over daily.
    daily = total_jobs / 30
    print(f"\n  estimated NEW jobs/day  ≈ {daily:.0f}")
    print(f"  estimated NEW QA/day    ≈ {total_qa/30:.0f}")
    if daily < 100:
        need = int((100 - daily) * 30 / max(1, total_jobs / max(1, len(live))))
        print(f"\n  → under 100/day. Add roughly {need} more boards, or enable")
        print(f"    the aggregator leg (RAPIDAPI_KEY) for staffing-agency postings.")
    else:
        print("\n  → target met. The aggregator leg adds staffing agencies on top.")

    if dead:
        print(f"\n  DEAD SLUGS ({len(dead)}):")
        for ats, c, r in dead:
            print(f"    {ats:11} {c['slug']:24} {c['label'][:24]:26} {r['why']}")

    if a.fix and dead:
        if len(dead) > 0.5 * len(tasks):
            print(f"\n  ! {len(dead)}/{len(tasks)} boards look dead — that is a network problem, "
                  "not stale slugs. Refusing to rewrite companies.yaml.")
            return
        retire_in_yaml(dead)
        print(f"\n  ✓ moved {len(dead)} dead slugs to `retired` in companies.yaml")
    elif dead:
        print("\n  run with --fix to move these to `retired`")


def retire_in_yaml(dead):
    """Remove each dead entry from ITS OWN section only (the same slug may be
    live under another ATS) and append it to `retired`, keeping the record."""
    lines = open(YAML, encoding="utf-8").read().split("\n")
    gone = {(ats, c["slug"]): r["why"] for ats, c, r in dead}
    out, section, moved = [], None, []
    for line in lines:
        m = re.match(r"^(\w+):", line)
        if m and not line.startswith(" "):
            section = m.group(1)
        e = re.match(r"^\s*-\s*\{slug:\s*([^,}]+),\s*label:\s*([^}]+)\}", line)
        if e and (section, e.group(1).strip()) in gone:
            moved.append(f"  - {{slug: {e.group(1).strip()}, label: {e.group(2).strip()}}}"
                         f"  # {gone[(section, e.group(1).strip())]}")
            continue
        out.append(line)
    txt = "\n".join(out)
    if re.search(r"^retired:\s*\[\]\s*$", txt, re.M):
        txt = re.sub(r"^retired:\s*\[\]\s*$", "retired:\n" + "\n".join(moved), txt, flags=re.M)
    elif re.search(r"^retired:\s*$", txt, re.M):
        txt = re.sub(r"^retired:\s*$", "retired:\n" + "\n".join(moved), txt, count=1, flags=re.M)
    else:
        txt = txt.rstrip("\n") + "\n\nretired:\n" + "\n".join(moved) + "\n"
    open(YAML, "w", encoding="utf-8").write(txt)


if __name__ == "__main__":
    main()
