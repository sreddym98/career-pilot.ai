#!/usr/bin/env bash
# One command from nothing to a board full of real jobs.
#   bash start.sh
set -e
cd "$(dirname "$0")"

G="\033[0;32m"; Y="\033[0;33m"; B="\033[0;34m"; N="\033[0m"
say(){ printf "${B}▸${N} %s\n" "$1"; }
win(){ printf "${G}✓${N} %s\n" "$1"; }
warn(){ printf "${Y}!${N} %s\n" "$1"; }

echo ""
echo "  CareerPilot — first run"
echo "  ───────────────────────"
echo ""

command -v python3 >/dev/null || { echo "Python 3 required"; exit 1; }

say "Installing dependencies…"
python3 -m pip install -q --disable-pip-version-check -r requirements.txt 2>&1 | tail -2 || true
win "dependencies ready"

[ -f .env ] || { cp .env.example .env; win "created .env"; }
export DATABASE_URL="${DATABASE_URL:-sqlite:///./careerpilot.db}"
export ENV="${ENV:-dev}"

say "Creating the database…"
python3 -c "from api.db import init_db; print('  tables:', len(init_db()))"
win "database ready"

echo ""
say "Pulling real jobs — no API key needed for this part."
echo "  379 company career boards + 4 free public APIs."
echo "  First run takes 2-4 minutes. Later runs are much faster."
echo ""

python3 ingest/run.py --once

echo ""
python3 ingest/run.py --report

echo ""
LIVE=$(python3 - <<'PY'
import os,sys
os.environ.setdefault("DATABASE_URL","sqlite:///./careerpilot.db")
sys.path.insert(0,".")
from api.db import SessionLocal
from api.models import Job
db=SessionLocal(); print(db.query(Job).filter(Job.active.is_(True)).count())
PY
)

if [ "$LIVE" -lt 30 ]; then
  warn "Only $LIVE jobs came back. Usually one of:"
  echo "    • no internet, or a proxy blocking outbound HTTPS"
  echo "    • corporate network filtering — try a personal connection"
  echo "    • some slugs in ingest/companies.yaml have gone stale"
  echo ""
  echo "  Check which boards are alive:  python3 ingest/verify_slugs.py"
else
  win "$LIVE live jobs in the database"
fi

echo ""
say "Starting the API on http://localhost:8000"
echo ""
echo "  ┌──────────────────────────────────────────────────────┐"
echo "  │  1. Open careerpilot.html in your browser             │"
echo "  │  2. More → Job feed → http://localhost:8000 → Connect  │"
echo "  │  3. The sample jobs disappear, real ones load          │"
echo "  └──────────────────────────────────────────────────────┘"
echo ""
echo "  Then, to keep it fresh:   python3 ingest/run.py --loop"
echo "  For contract roles:       add RAPIDAPI_KEY to .env (see below)"
echo ""

exec python3 -m uvicorn api.main:app --port 8000 --host 0.0.0.0
