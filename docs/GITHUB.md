# Pushing this to GitHub

Private repo. Copy-paste from here.

---

## Before the first push — two minutes

```bash
bash scripts/setup-hooks.sh          # blocks secrets from ever being committed
bash scripts/check-secrets.sh --all  # scan what's here now
```

Both must pass. If the scanner flags anything, remove it **and rotate the key** —
assume anything written into a repo is already compromised.

Also confirm your `.env` is not tracked:

```bash
git status --porcelain | grep -E '\.env$' && echo "STOP — .env would be committed"
```

---

## Create the private repo

### With GitHub CLI

```bash
gh auth login
cd careerpilot
git init
git add .
git commit -m "careerpilot.ai — initial commit"
gh repo create careerpilot --private --source=. --remote=origin --push
```

Two commands and you're done. `--private` is not the default, so don't drop it.

### Without the CLI

1. github.com/new → name `careerpilot` → **Private** → create nothing else
   (no README, no .gitignore, no license — this repo already has them)

2. Then:

```bash
cd careerpilot
git init
git add .
git commit -m "careerpilot.ai — initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/careerpilot.git
git push -u origin main
```

Authentication: GitHub stopped accepting passwords in 2021. Use a personal
access token as the password —
Settings → Developer settings → Personal access tokens → Fine-grained →
scope it to just this repo, `Contents: Read and write`.

---

## Using GitHub Copilot to push

Copilot Chat can run these for you, but it won't guess your intent:

```
Initialise a git repo here, stage everything, commit as
"careerpilot.ai — initial commit", and push to a NEW PRIVATE
GitHub repo called careerpilot.
```

Two things to check afterwards, because Copilot won't:

1. **The repo is actually private.** Open it and look for the `Private` badge
   next to the name. If it says Public, change it immediately:
   Settings → General → Danger Zone → Change visibility.

2. **No `.env` was committed.** Run `git ls-files | grep .env` — you should see
   only `.env.example`.

---

## Day-to-day

```bash
git checkout -b feature/live-job-feed
# work
git add .
git commit -m "Wire the frontend to the live job API"   # hook scans automatically
git push -u origin feature/live-job-feed
```

Commit messages that will make sense to you in six months:

```
Add Adzuna connector to the ingest pipeline
Fix visa parser missing "unable to sponsor"
Cut resume generation to one API call per role
```

---

## If you commit a secret by accident

The hook makes this unlikely, but if it happens:

```bash
# 1. Rotate the key FIRST. Always. Before anything else.
# 2. Then clean the history:
pip install git-filter-repo
git filter-repo --path server/.env --invert-paths --force
git push origin --force --all
```

Rewriting history does not fully remove it — GitHub keeps unreachable objects,
and anyone who cloned still has it. **Rotation is the only real fix.** The
cleanup is housekeeping.

---

## Branch protection — worth 60 seconds

Settings → Branches → Add rule for `main`:

- Require a pull request before merging
- Require status checks: `Secret scan`, `Server tests`, `Frontend tests`

Even solo, this stops you force-pushing over working code at 1am.

---

## What CI runs on every push

`.github/workflows/ci.yml`:

| Job | Checks |
|---|---|
| Secret scan | every tracked file, all key formats |
| Server tests | visa parser (15), billing (15), AI retry (14), API (38) |
| Frontend tests | JS syntax, extension manifest |
| No secrets in frontend | `web/index.html` contains no keys |

GitHub Actions is free on private repos up to 2,000 minutes a month. These
run in about two.
