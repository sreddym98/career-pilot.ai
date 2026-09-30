# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""H-1B sponsor data + board discovery (offline; network probes are injected).

    cd server && DATABASE_URL=sqlite:///./ci_sponsors.db ENV=dev python3 test_sponsors.py
"""
import os, sys
os.environ.setdefault("DATABASE_URL", "sqlite:///./ci_sponsors.db")
os.environ.setdefault("ENV", "dev")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: os.remove("ci_sponsors.db")
except OSError: pass

P = F = 0
def ok(name, cond, detail=""):
    global P, F
    if cond: P += 1
    else:
        F += 1; print("  FAIL", name, detail)

from api.db import init_db, SessionLocal
from api.sponsors import brand_key, clean_name, sponsors_for
from ingest import sponsors as S
init_db(); db = SessionLocal()

ok("brand strips legal+generic", brand_key("AMAZON.COM SERVICES LLC") == "amazon")
ok("brand keeps identity", brand_key("Stripe, Inc.") == "stripe")
ok("brand no false prefix", brand_key("First Solar Inc") != brand_key("First American"))
ok("clean_name", clean_name("Acme Payments Corp") == "acme payments")

CSV = ('"Fiscal Year","Employer (Petitioner) Name","Tax ID","Industry (NAICS) Code","Petitioner City",'
       '"Petitioner State","Petitioner Zip Code","Initial Approval","Initial Denial","Continuing Approval","Continuing Denial"\n'
       '2022,"STRIPE, INC.",1,51,"SAN FRANCISCO",CA,94103,"10",0,"5",0\n'
       '2023,"STRIPE, INC.",1,51,"SAN FRANCISCO",CA,94103,"1,200",2,"300",0\n'
       '2023,"AMAZON.COM SERVICES LLC",2,45,SEATTLE,WA,98109,"3,000",0,"2,000",0\n'
       '2023,"AMAZON WEB SERVICES, INC.",3,51,SEATTLE,WA,98109,"500",0,"616",0\n'
       '2023,"ZERO CO",4,51,X,NY,1,0,0,0,0\n')
agg = S.aggregate(S.parse_rows(CSV))
ok("latest FY used", agg["stripe"]["fy"] == 2023 and agg["stripe"]["approvals"] == 1500, agg.get("stripe"))
ok("entities summed by brand", agg["amazon"]["approvals"] == 5000, agg.get("amazon"))
ok("AWS kept as its own brand", agg["amazon web"]["approvals"] == 1116, agg.get("amazon web"))
try:
    list(S.parse_rows("a,b\n1,2\n")); ok("bad columns raise", False)
except RuntimeError: ok("bad columns raise", True)

n = S.store_sponsors(db, agg)
ok("zero-approval brand skipped", n == len(agg) - 1, n)
m = sponsors_for(db, ["Stripe", "Stripe, Inc.", "Nobody Labs", "Amazon"])
ok("job company matched", m["Stripe"]["approvals"] == 1500 and m["Stripe"]["fy"] == 2023)
ok("no match -> absent", "Nobody Labs" not in m)
ok("re-store idempotent", S.store_sponsors(db, agg) == n)

ok("slug candidates", S.slug_candidates("Acme Payments Inc") == ["acmepayments", "acme-payments"] and S.slug_candidates("Stripe Inc") == ["stripe"] and "salesforce" in S.slug_candidates("Salesforce Inc"))
ok("short first word not guessed", "first" not in S.slug_candidates("First American Financial"))

calls = []
def fake(name):
    calls.append(name)
    return ("greenhouse", "stripe", 12) if "STRIPE" in name.upper() else None
r = S.discover(db, top=10, probe=fake)
ok("discover found one", r["found"] == 1 and r["probed"] == len(agg) - 1, r)
ok("boards exposed to ingest", ("greenhouse", "stripe", "Stripe") in S.discovered_boards(db))
r2 = S.discover(db, top=10, probe=fake)
ok("recent results not re-probed", r2["probed"] == 0 and len(calls) == len(agg) - 1, r2)

from ingest import run
boards = run._discovered_extra(db, [("greenhouse", "stripe", "Stripe")])
ok("yaml wins on duplicate", boards == [])
ok("discovered added when new", run._discovered_extra(db, []) == [("greenhouse", "stripe", "Stripe")])

print(f"sponsors: {P} passed, {F} failed")
sys.exit(1 if F else 0)
