#!/usr/bin/env bash
# Refuses to let a secret reach a commit.
# Installed as a pre-commit hook by scripts/setup-hooks.sh
set -uo pipefail

RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[0;33m'; NC='\033[0m'
FOUND=0

# Real key shapes, not guesses
declare -a PATTERNS=(
  'sk_live_[0-9a-zA-Z]{20,}|Stripe LIVE secret key'
  'sk_test_[0-9a-zA-Z]{20,}|Stripe test secret key'
  'rk_live_[0-9a-zA-Z]{20,}|Stripe restricted key'
  'whsec_[0-9a-zA-Z]{20,}|Stripe webhook secret'
  'sk-ant-[0-9a-zA-Z_-]{20,}|Anthropic API key'
  'sk-[a-zA-Z0-9]{40,}|OpenAI-style API key'
  'gh[pousr]_[0-9a-zA-Z]{30,}|GitHub token'
  'AKIA[0-9A-Z]{16}|AWS access key id'
  'AIza[0-9A-Za-z_-]{35}|Google API key'
  'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|JWT (possible session token)'
  '-----BEGIN [A-Z ]*PRIVATE KEY-----|Private key block'
  'xox[baprs]-[0-9a-zA-Z-]{10,}|Slack token'
  'postgres(ql)?://[^:]+:[^@]+@|Postgres URL with a password'
  'mongodb(\+srv)?://[^:]+:[^@]+@|MongoDB URL with a password'
)

if [ "${1:-}" = "--all" ]; then
  FILES=$(git ls-files)
  echo "Scanning every tracked file…"
else
  FILES=$(git diff --cached --name-only --diff-filter=ACM)
fi
[ -z "$FILES" ] && exit 0

for f in $FILES; do
  [ -f "$f" ] || continue
  case "$f" in
    */check-secrets.sh|*.min.js|*.lock|package-lock.json) continue ;;
  esac
  for entry in "${PATTERNS[@]}"; do
    pat="${entry%%|*}"; label="${entry##*|}"
    # Ignore obvious placeholders — docs need to show the shape of a value
    hits=$(grep -nEI "$pat" "$f" 2>/dev/null \
      | grep -viE 'xxxx|example|placeholder|your-|your_|<[a-z_]+>|\.\.\.|dummy|sample|\bfake\b' \
      | grep -viE ':(pass|password|passwd|secret|token|changeme|dev|test|yourpassword)@' \
      || true)
    if [ -n "$hits" ]; then
      printf "${RED}✗ %s${NC} in ${YEL}%s${NC}\n" "$label" "$f"
      echo "$hits" | head -3 | sed 's/^/    /' | cut -c1-110
      FOUND=1
    fi
  done
done

# .env must never be tracked
for env in $(git ls-files | grep -E '(^|/)\.env($|\.)' | grep -v '\.env\.example' || true); do
  printf "${RED}✗ %s is tracked by git${NC} — run: git rm --cached %s\n" "$env" "$env"
  FOUND=1
done

if [ "$FOUND" = "1" ]; then
  cat <<'MSG'

  ─────────────────────────────────────────────────────────────
  Commit blocked. A secret would have been committed.

  Remove it from the file, then rotate the key anyway — assume
  anything written to disk in a repo is already compromised.

    Stripe     Dashboard → Developers → API keys → Roll key
    Anthropic  console.anthropic.com → API keys → revoke
    GitHub     Settings → Developer settings → revoke token

  Secrets belong in .env, which .gitignore already excludes.
  To override once (you had better be sure): git commit --no-verify
  ─────────────────────────────────────────────────────────────
MSG
  exit 1
fi

printf "${GRN}✓${NC} no secrets detected\n"
exit 0
