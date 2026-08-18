# Go live — real jobs on your board

Everything is built. This is the shortest path from zip to a working portal.

---

## Why you're seeing 11 jobs

Those are **samples baked into `careerpilot.html`** so the UI works before any
setup. They are not the board.

The real board comes from `ingest/run.py` — 379 company career boards plus 6
aggregators. It has never run on your machine yet.

I couldn't run it for you: my sandbox blocks every domain except GitHub and
PyPI. The proxy returns `Host not in allowlist: boards-api.greenhouse.io`.
On your machine there is no such block.

---

## One command

```bash
unzip careerpilot-backend.zip
cd be
bash start.sh
```

That installs dependencies, creates the database, **pulls real jobs**, prints a
volume report, and starts the API. First run takes 2–4 minutes.

Then point the frontend at it. Open `careerpilot.html` in an editor and set
one line near the top of the script:

```js
const API_ENDPOINT = "http://localhost:8000";   // or your deployed API
```

That's it. Customers never see a setup screen — there isn't one in the product.
For your own testing on staging you can also open `careerpilot.html?setup=1`,
which reveals an internal panel that isn't linked from anywhere.

---

## What you get without paying anything

| Source | Roles | Cost |
|---|---|---|
| 379 ATS boards (Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Recruitee, JazzHR, Breezy, Teamtailor) | ~57 full-time | free |
| Remotive, RemoteOK, Arbeitnow | ~40–80 | free |
| **Free total** | **~100–140** | **$0** |

## What you need for contract roles

**This is the one that matters for your audience.** Staffing agencies post to
Dice and job boards, not to company ATS. Without this the contract side stays
near zero — which is exactly what you're seeing.

```bash
# .env
RAPIDAPI_KEY=...          # rapidapi.com/letscrape/api/jsearch — ~$30/mo
                          # → 120–200 contract roles
ADZUNA_APP_ID=...         # developer.adzuna.com — free tier
ADZUNA_APP_KEY=...        # → 40–80 more
USAJOBS_KEY=...           # developer.usajobs.gov — free
USAJOBS_EMAIL=...         # → 40–80 federal QA roles
```

With all four: **250–400 live roles**, comfortably past your 100 full-time /
200 contract targets. Two of the three keys are free.

---

## Keeping it fresh

```bash
python3 ingest/run.py --loop      # aggregators every 10 min, ATS every 2h
python3 ingest/run.py --report    # volume against targets
python3 ingest/verify_slugs.py    # which of the 379 boards are still alive
```

New jobs surface in **10–20 minutes**. Not every 5 minutes, deliberately —
379 boards at that rate is 115,000 requests/day and gets your IP blocked
within days for no extra freshness. See `ingest/scheduler.py` for the maths.

---

## Deploy

```bash
railway up
railway variables set ANTHROPIC_API_KEY=... RAPIDAPI_KEY=... \
  STRIPE_SECRET_KEY=... STRIPE_WEBHOOK_SECRET=... DATABASE_URL=...
railway cron "*/10 * * * *" "python ingest/run.py --fast"
railway cron "0 */2 * * *"  "python ingest/run.py --once"
```

Frontend: drop `careerpilot.html` on Cloudflare Pages as `index.html`.

---

## Pre-launch checklist

- [ ] `bash start.sh` returns 100+ live jobs
- [ ] `API_ENDPOINT` set in `careerpilot.html` — otherwise it stays in demo mode
- [ ] `RAPIDAPI_KEY` set — otherwise no contract roles
- [ ] `python3 ingest/verify_slugs.py --fix` — prunes dead boards
- [ ] `python3 setup_stripe.py` — creates products, prints price IDs
- [ ] `stripe listen --forward-to localhost:8000/api/billing/webhook` → `whsec_…`
- [ ] Test a checkout with `4242 4242 4242 4242`
- [ ] Load the extension: `chrome://extensions` → Load unpacked → `extension/`
- [ ] Privacy policy + terms — Stripe and Chrome both require them
- [ ] Check "CareerPilot" on USPTO TESS before printing anything
