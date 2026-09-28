# Job ingest

Pulls QA/SDET jobs into the `jobs` table that the board and autopilot read.
Runs from GitHub Actions (`.github/workflows/ingest.yml`), not as a server.

## What runs when

| Schedule | Command | Sources |
|---|---|---|
| Even hours (UTC) | `python ingest/run.py --once` | aggregators, then ~373 ATS boards (Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Recruitee, JazzHR, Breezy, Teamtailor) |
| Odd hours | `python ingest/run.py --fast` | aggregators only |
| Weekly (add to workflow) | `python ingest/run.py --prune` | none — deletes jobs unseen for 45 days |

Run from `server/` with `DATABASE_URL` (Neon) and `ENV=prod`. On GitHub Actions the run stops fetching after 1000s (`--max-seconds`) so it exits cleanly inside the 20-minute limit; unreached boards are picked up next run (board order is shuffled).

## Keys

| Var | Cost | Signup | Adds |
|---|---|---|---|
| none (Remotive, RemoteOK, Arbeitnow, all ATS boards) | free | no | base volume |
| `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` | free tier (1,000 calls/mo) | developer.adzuna.com | ~40-80 mixed roles |
| `USAJOBS_KEY` + `USAJOBS_EMAIL` | free | developer.usajobs.gov | ~40-80 federal QA roles |
| `RAPIDAPI_KEY` (JSearch) | paid, ~$30/mo | rapidapi.com | 120-200 contract/C2C roles (the only reliable staffing-agency source) |

Missing keys are skipped and listed in the log. Both Adzuna vars / both USAJobs vars are required.
Remotive asks for at most a few fetches a day, so it runs every 6 hours (`INGEST_REMOTIVE_EVERY_HOURS`).

## Expected volumes

Keyless + boards: roughly 100+ live full-time QA roles. Contract (200+) needs `RAPIDAPI_KEY`. `--report` prints live counts against these targets, jobs added in the last 24h/7d, and how many carry `required_skills`.

## Safety rules (why data does not vanish)

- A job is deactivated only by a **clean, non-empty fetch of its own board** that no longer lists it. Errors, timeouts, empty listings, partial fetches and a sudden >80% drop on a board (5+ live) never deactivate anything.
- Aggregator jobs age out after 21 days unseen, only for feeds that fetched cleanly this run.
- Re-runs are idempotent: same `source|id` fingerprint, `first_seen` is never reset, `seen_count` +1 per run; a job that returns after being inactive is marked `relisted`.
- Each source commits separately; a bad row costs that row, a bad board costs that board.
- `--prune` deletes unreferenced rows and only deactivates ones an application points at; it refuses to run if nothing was seen in the last 3 days.
- `required_skills` is extracted from title + description with a fixed vocabulary (`ingest/skills.py`); nothing is inferred. SmartRecruiters carries no description, so it is tagged from the title only.
- `seed.py` fabricates demo data and exits unless `ENV=dev` (`--force-i-know` overrides; do not).

## Run once by hand

```
cd server
DATABASE_URL=... ENV=prod python ingest/run.py --once --max-seconds 600
DATABASE_URL=... ENV=prod python ingest/run.py --report
```
Exit codes: `0` completed (some boards may have failed), `1` every attempted source failed, `2` database unreachable.

## Verify slugs

```
python ingest/verify_slugs.py            # probe every board with the real connectors
python ingest/verify_slugs.py --fix      # move 404s to `retired` in companies.yaml
```
Only definite 404s are retired; timeouts and 429s are left alone. `--fix` refuses if over half the boards look dead (that is a network problem).

## A healthy log

```
[agg] aggregators…
[ats] 373 boards…
  INGEST SUMMARY status=ok mode=full new=40 relisted=2 seen=900 filtered=15000 bad_rows=0 deactivated=25 sources_ok=370/376 failed=6 deferred=0 duration=240s
```
Healthy: `status=ok` or `degraded` with a handful of failed boards (stale slugs), `bad_rows=0`, duration well under 1000s, `new` > 0 on most runs. Investigate: `status=failed` (exit 1), `deferred` > 0 every run (too many boards for the budget), `sweep skipped — suspicious drop` on the same board repeatedly, or `deactivated` in the hundreds. The summary is also written to the Actions job summary page.
