B=${API:-http://localhost:8000}
P=0;F=0
chk(){ if echo "$2" | grep -q "$3"; then echo "  ✓ $1"; P=$((P+1)); else echo "  ✗ $1"; echo "      got: $(echo "$2"|head -c 200)"; F=$((F+1)); fi }
jobcheck(){
  printf '%s' "$1" | python -c '
import json, sys
d=json.load(sys.stdin); jobs=d.get("jobs", []); mode=sys.argv[1]
ok="jobs" in d
if mode=="h1b": ok &= all(j.get("visa",{}).get("h1b") != "n" for j in jobs)
elif mode=="usc": ok &= all(j.get("visa",{}).get("usc") != "n" for j in jobs)
elif mode=="contract": ok &= all(j.get("employment") == "contract" for j in jobs)
elif mode=="f500": ok &= all(j.get("is_fortune500") is True for j in jobs)
elif mode=="staffing": ok &= all(j.get("company_type") == "staffing" for j in jobs)
elif mode=="playwright": ok &= isinstance(jobs, list)
elif mode=="reposts": ok &= all(j.get("seen_count",0) < 3 for j in jobs)
print("ok" if ok else "bad")
' "$2"
}
INVITE_ONE="api-${RANDOM:-0}-one@example.com"
INVITE_TWO="api-${RANDOM:-0}-two@example.com"

echo "── PROFILE ──"
R=$(curl -s -m5 $B/api/profile)
chk "GET /api/profile"                "$R" '"name"'
chk "  total_label computed"          "$R" '"total_label":"7 yrs 7 mos"'
chk "  3 positions"                   "$R" '"Tata Consultancy Services"'
chk "  per-role duration"             "$R" '"duration_label":"4 yrs 4 mos"'
chk "  employment gap detected"       "$R" '"months":4'
chk "  skills loaded"                 "$R" 'Playwright'

echo "── JOBS ──"
R=$(curl -s -m5 "$B/api/jobs?limit=50")
chk "GET /api/jobs"                   "$(jobcheck "$R" base)" '^ok$'
chk "  visa flags present"            "$R" '"visa"'
chk "  competition estimated"         "$R" '"competition"'
chk "  referral paths joined"         "$R" '"referrals"'

R=$(curl -s -m5 "$B/api/jobs?auth=h1b&limit=50")
chk "H1B filter hides exclusions"     "$(jobcheck "$R" h1b)" '^ok$'

R=$(curl -s -m5 "$B/api/jobs?auth=usc&limit=50")
chk "USC filter hides exclusions"     "$(jobcheck "$R" usc)" '^ok$'

R=$(curl -s -m5 "$B/api/jobs?employment=contract&limit=50")
chk "employment filter"               "$(jobcheck "$R" contract)" '^ok$'
R=$(curl -s -m5 "$B/api/jobs?company=f500&limit=50")
chk "fortune500 filter"               "$(jobcheck "$R" f500)" '^ok$'
R=$(curl -s -m5 "$B/api/jobs?company=staffing&limit=50")
chk "staffing filter"                 "$(jobcheck "$R" staffing)" '^ok$'
R=$(curl -s -m5 "$B/api/jobs?q=playwright&limit=50")
chk "text search"                     "$(jobcheck "$R" playwright)" '^ok$'
R=$(curl -s -m5 "$B/api/jobs?hide_reposts=true&limit=50")
chk "hide reposts"                    "$(jobcheck "$R" reposts)" '^ok$'
R=$(curl -s -m5 "$B/api/jobs?limit=3")
chk "pagination"                      "$R" '"limit":3'
R=$(curl -s -m5 -w '\n%{http_code}' "$B/api/jobs/not-a-real-fingerprint")
chk "unknown job returns 404"          "$R" '404'

echo "── REFERRALS ──"
R=$(curl -s -m5 $B/api/referrals)
chk "GET /api/referrals"              "$R" '"active":2'
chk "  bonus = 2 x 100"               "$R" '"bonus_credits":200'
chk "  allowance = 400 + 200"         "$R" '"allowance":600'
chk "  emails masked"                 "$R" '•'
chk "  share link"                    "$R" 'join/santoshreddy'
R=$(curl -s -m5 -X POST $B/api/referrals/invite -H 'Content-Type: application/json' -d "{\"emails\":[\"$INVITE_ONE\",\"$INVITE_TWO\"]}")
chk "POST invite"                     "$R" '"invited":2'
R=$(curl -s -m5 -X POST $B/api/referrals/invite -H 'Content-Type: application/json' -d "{\"emails\":[\"$INVITE_ONE\"]}")
chk "  dedupes repeat invite"         "$R" '"invited":0'

echo "── CREDITS ──"
R=$(curl -s -m5 $B/api/ai/credits)
chk "GET /api/ai/credits"             "$R" '"allowance":600'
chk "  plan reflected"                "$R" '"plan":"pro"'

echo "── POSITIONS CRUD ──"
R=$(curl -s -m5 -X POST $B/api/positions -H 'Content-Type: application/json' \
  -d '{"company":"Ellipsis Health","role":"Staff SDET","started_on":"2015-01-01","finished_on":"2017-06-30","location":"Remote","bullets":["Built first automated regression suite"]}')
chk "POST /api/positions"             "$R" '"duration_label":"2 yrs 6 mos"'
PID=$(echo "$R" | sed 's/.*"id":"\([^"]*\)".*/\1/')
R=$(curl -s -m5 $B/api/profile)
chk "  total grew to 10y 1m"          "$R" '"total_label":"10 yrs 1 mo"'
R=$(curl -s -m5 -X PUT $B/api/positions/$PID -H 'Content-Type: application/json' \
  -d '{"company":"Ellipsis Health","role":"Principal SDET","started_on":"2015-01-01","finished_on":"2017-06-30","bullets":["Updated bullet"]}')
chk "PUT /api/positions/{id}"         "$R" '"duration_label"'
R=$(curl -s -m5 -X POST $B/api/positions -H 'Content-Type: application/json' \
  -d '{"company":"X","role":"Y","started_on":"2020-01-01","finished_on":"2019-01-01","bullets":["b"]}')
chk "  rejects end-before-start"      "$R" 'before the start'
R=$(curl -s -m5 -X POST $B/api/positions -H 'Content-Type: application/json' \
  -d '{"company":"X","role":"Y","started_on":"2020-01-01","bullets":[]}')
chk "  rejects empty bullets"         "$R" 'at least one bullet'
R=$(curl -s -m5 -X DELETE $B/api/positions/$PID)
chk "DELETE /api/positions/{id}"      "$R" '"deleted":true'
R=$(curl -s -m5 $B/api/profile)
chk "  total back to 7y 7m"           "$R" '"total_label":"7 yrs 7 mos"'

echo "── PUBLIC PROFILE (no auth) ──"
R=$(curl -s -m5 $B/api/u/santoshreddy)
chk "GET /api/u/{slug}"               "$R" '"headline"'
chk "  no email exposed"              "$(echo $R | grep -c 'dev@careerpilot')" '^0$'
R=$(curl -s -m5 $B/api/u/nonexistent)
chk "  404 on unknown slug"           "$R" 'not found'

echo ""
echo "════════════════════════════"
echo "PASS $P    FAIL $F"
test "$F" -eq 0
