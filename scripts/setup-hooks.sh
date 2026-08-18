#!/usr/bin/env bash
# Run once after cloning: bash scripts/setup-hooks.sh
set -e
cd "$(git rev-parse --show-toplevel)"
mkdir -p .git/hooks
cat > .git/hooks/pre-commit <<'HOOK'
#!/usr/bin/env bash
exec bash scripts/check-secrets.sh
HOOK
chmod +x .git/hooks/pre-commit
echo "✓ pre-commit hook installed — secrets can no longer be committed"
echo "  scan everything now:  bash scripts/check-secrets.sh --all"
