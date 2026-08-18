#!/usr/bin/env bash
# Runs every frontend test against web/index.html and prints a summary.
# From repo root: bash web/tests/run-all.sh
cd "$(dirname "$0")"

if [ ! -d node_modules ]; then
  echo "Installing test dependencies (jsdom)..."
  npm install --silent
  echo ""
fi

TOTAL_PASS=0
TOTAL_FAIL=0
FAILED_FILES=()

for f in *.js; do
  OUT=$(node "$f" 2>&1)
  LINE=$(echo "$OUT" | grep -oE 'PASS [0-9]+ +FAIL [0-9]+' | tail -1)
  if [ -z "$LINE" ]; then
    printf "  %-22s CRASHED\n" "$f"
    FAILED_FILES+=("$f")
    continue
  fi
  P=$(echo "$LINE" | grep -oE 'PASS [0-9]+' | grep -oE '[0-9]+')
  FAIL=$(echo "$LINE" | grep -oE 'FAIL [0-9]+' | grep -oE '[0-9]+')
  printf "  %-22s PASS %-4s FAIL %s\n" "$f" "$P" "$FAIL"
  TOTAL_PASS=$((TOTAL_PASS + P))
  TOTAL_FAIL=$((TOTAL_FAIL + FAIL))
  if [ "$FAIL" != "0" ]; then FAILED_FILES+=("$f"); fi
done

echo ""
echo "════════════════════════════════════"
echo "TOTAL: $TOTAL_PASS passed, $TOTAL_FAIL failed"
if [ ${#FAILED_FILES[@]} -gt 0 ]; then
  echo "Files with failures: ${FAILED_FILES[*]}"
  exit 1
fi
echo "✓ everything passes"
