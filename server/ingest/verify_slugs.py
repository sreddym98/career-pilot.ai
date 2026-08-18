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

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

HERE = __file__.rsplit("/", 1)[0]
YAML = f"{HERE}/companies.yaml"
UA = {"User-Agent": "careerpilot-verifier/1.0 (+contact@yourdomain.com)"}
TIMEOUT = 15

ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    "lever":      "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby":      "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}

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
    url = ENDPOINTS[ats].format(slug=slug)
    try:
        r = requests.get(url, headers=UA, timeout=TIMEOUT)
    except Exception as e:
        return {"ok": False, "n": 0, "qa": 0, "why": type(e).__name__}
    if r.status_code == 404:
        return {"ok": False, "n": 0, "qa": 0, "why": "404 — slug not found"}
    if r.status_code != 200:
        return {"ok": False, "n": 0, "qa": 0, "why": f"HTTP {r.status_code}"}
    try:
        d = r.json()
    except Exception:
        return {"ok": False, "n": 0, "qa": 0, "why": "not JSON"}

    if ats == "greenhouse":
        jobs = d.get("jobs", [])
        titles = [j.get("title", "") for j in jobs]
    elif ats == "lever":
        jobs = d if isinstance(d, list) else []
        titles = [j.get("text", "") for j in jobs]
    else:
        jobs = d.get("jobs", [])
        titles = [j.get("title", "") for j in jobs]

    qa = sum(1 for t in titles if QA_WORDS.search(t))
    return {"ok": True, "n": len(jobs), "qa": qa, "why": "",
            "sample": [t for t in titles if QA_WORDS.search(t)][:3]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="move dead slugs to `retired`")
    ap.add_argument("--qa", action="store_true", help="show QA/SDET titles found")
    ap.add_argument("--workers", type=int, default=12)
    a = ap.parse_args()

    data = load()
    tasks = [(ats, c) for ats in ENDPOINTS for c in data.get(ats, [])]
    print(f"Probing {len(tasks)} boards across {len(ENDPOINTS)} ATS vendors…\n")

    live, dead, t0 = [], [], time.time()
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
            else:
                dead.append((ats, c, r))
                print(f"  ✗ {c['label'][:26]:28} {ats:11} {r['why']}")
            if done % 50 == 0:
                print(f"    … {done}/{len(tasks)}")

    total_jobs = sum(r["n"] for _, _, r in live)
    total_qa = sum(r["qa"] for _, _, r in live)
    empty = sum(1 for _, _, r in live if r["n"] == 0)

    print("\n" + "=" * 62)
    print(f"  live boards      {len(live)} / {len(tasks)}  ({len(live)/max(1,len(tasks))*100:.0f}%)")
    print(f"  dead slugs       {len(dead)}")
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
        txt = open(YAML, encoding="utf-8").read()
        for ats, c, _ in dead:
            txt = re.sub(rf"^\s*-\s*\{{slug:\s*{re.escape(c['slug'])},.*$\n", "",
                         txt, flags=re.M)
        block = "\n".join(f"  - {{slug: {c['slug']}, label: {c['label']}}}  # {r['why']}"
                          for ats, c, r in dead)
        txt = txt.replace("retired: []", "retired:\n" + block)
        open(YAML, "w", encoding="utf-8").write(txt)
        print(f"\n  ✓ moved {len(dead)} dead slugs to `retired` in companies.yaml")
    elif dead:
        print("\n  run with --fix to move these to `retired`")


if __name__ == "__main__":
    main()
