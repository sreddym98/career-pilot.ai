# careerpilot.ai — backend + extension

Four things you asked for, all built and tested:

| | Status |
|---|---|
| **Database** | 9 tables, portable Postgres/SQLite, seed data included |
| **API server** | 16 endpoints, **38/38 tests passing against a live server** |
| **AI proxy** | Your Anthropic key never reaches a browser |
| **Browser extension** | CareerPilot Autofill, **71/71 tests** — install via `extension/INSTALL.md` |
| **Company list** | **317 ATS slugs** in `ingest/companies.yaml` + live verifier |

---

## Run it — three commands

```bash
pip install -r requirements.txt
python seed.py          # creates the DB, loads sample data
make dev                # http://localhost:8000/docs
```

No Postgres needed to start. It falls back to SQLite automatically, and with no
Supabase key set it signs you in as a local dev user so every endpoint works
immediately. Switch to Postgres later by setting one env var.

```bash
make test               # visa parser + all 38 API tests
```

---

## 1. Database

`api/models.py` — users, positions, skills, jobs, applications, ai_cache,
courses, connections, referrals.

**Durations are never stored.** `Position.months` computes from
`started_on`/`finished_on` on read. Storing "2 yrs 4 mos" means it's wrong the
moment the month rolls over — this is the bug you spotted in the frontend, fixed
properly at the schema level.

Same models run on both engines: `UUIDStr`, `StrArray`, and `JSONish` map to
native Postgres types in production and JSON-in-TEXT on SQLite.

## 2. API server

```
GET    /api/jobs                 filters: auth, fields, families, employment,
                                 modes, company, fresh_days, hide_reposts
GET    /api/jobs/{fingerprint}
GET    /api/profile              positions + computed durations + gaps
POST   /api/positions            validates dates and bullets
PUT    /api/positions/{id}
DELETE /api/positions/{id}       refuses to delete your last role
GET    /api/u/{slug}             public profile, no auth, no email exposed
POST   /api/ai/resume            one call per role
POST   /api/ai/cover-letter
GET    /api/ai/credits
GET    /api/referrals
POST   /api/referrals/invite
POST   /api/referrals/attribute/{code}
POST   /api/billing/checkout
POST   /api/billing/portal       self-serve cancel
POST   /api/billing/webhook      signature-verified
```

Two behaviours worth knowing:

**Visa filtering hides only explicit exclusions.** `?auth=h1b` removes postings
that say they won't sponsor. Postings that say nothing stay visible as
`'u'` — treating silence as rejection would delete most of the board.

**Competition is estimated, never faked.** Derived from posting age and repost
count. No job board publishes real applicant numbers; inventing one is how you
lose a user permanently.

## 3. AI proxy — read this before deploying

The prototype calls `api.anthropic.com` **from the browser**. That works inside
Claude artifacts because the key is injected server-side. On your own domain it
would hand your API key to every visitor, and someone would drain your account.

`api/routers/ai.py` is the fix. Point the frontend at `/api/ai/*` instead.

It also enforces the economics:

- **Plan gate** — free users can't call it at all
- **Credit gate** — 150/month Pro, +100 per active referral, 500 ceiling
- **Cache** — `sha256(resume + jd + task)`. A repeat request costs you nothing.
  This is the difference between a viable subscription and one that loses money
  on power users.

## 4. Browser extension — CareerPilot Autofill

**Installable right now** — see `extension/INSTALL.md`. Takes about a minute
via Developer Mode; no store approval needed for your own use.

```
chrome://extensions → Developer mode → Load unpacked → pick extension/
```

Then open `extension/test-form.html` and click ✈ → Fill this form. It's a mock
application with the real field names Greenhouse, Workday, Lever, and iCIMS use
— 16 fields fill, 6 stay deliberately blank, nothing submits.

Detects Workday, Greenhouse, Lever, Ashby, iCIMS, SmartRecruiters. Fills name,
email, phone, location, LinkedIn, GitHub, portfolio.

**What it deliberately will not do:**

- **Never submits.** Fill only. You press the button.
- **Never answers salary.** Highlighted amber: *"You decide this number."*
- **Never answers sponsorship.** Getting that wrong costs the application.
- **Never answers demographics.** Voluntary, left blank.
- **Never overwrites** anything you already typed.

Field matching tests each attribute separately — name, id, placeholder,
aria-label, `data-automation-id`, and the associated `<label>`. Joining them
into one string breaks anchored patterns when an opaque id like `f1` sorts ahead
of the real label; that bug made iCIMS fill zero fields until it was caught.

## 5. Wiring the frontend

`api_client.js` — include before the app script:

```html
<script src="api_client.js"></script>
<script>
  CP_API.configure("https://api.careerpilot.ai", supabaseJwt);
  const { EXP, J, SKILLS } = await hydrateFromAPI();
</script>
```

Then replace the three direct `fetch("https://api.anthropic.com/...")` calls
with `CP_API.buildResume(...)` and `CP_API.coverLetter(...)`.

## Deploy

```bash
railway up
railway variables set ANTHROPIC_API_KEY=... STRIPE_SECRET_KEY=... \
  STRIPE_WEBHOOK_SECRET=... SUPABASE_JWT_SECRET=... DATABASE_URL=...
railway run python -c "from api.db import init_db; init_db()"
railway cron "0 6 * * *" "python ingest/ingest.py --run"
railway cron "0 7 * * *" "python -c 'from api.db import SessionLocal;from api import credits;credits.qualify_pending(SessionLocal())'"
```

---

## 6. Job sources — `ingest/companies.yaml`

**317 ATS slugs**, grouped by sector and weighted toward where SDET roles
actually are: payments/fintech, healthcare, data infrastructure, dev tools,
security.

| ATS | Companies |
|---|---|
| Greenhouse | 214 |
| Lever | 63 |
| Ashby | 40 |

### Verify before trusting it

```bash
make verify        # probe every board, report live/dead + job counts
make verify-fix    # move dead slugs to `retired`
```

Company slugs go stale — firms migrate ATS vendors, get acquired, or rename
their board. **Expect 10–20% of any curated list to be dead on day one.** The
verifier probes all 317 in parallel, counts real jobs, counts QA/SDET titles
specifically, and estimates your daily new-job volume. Run it before your first
ingest and monthly after.

```bash
make ingest        # daily pull
make report        # what came in over the last 24h
```

### Two honest limits

**Fortune 500 won't come from this file.** They mostly run Workday, which has
no clean public API — every tenant has its own endpoint shape. F500 coverage
comes from the aggregator leg (`RAPIDAPI_KEY`), not from ATS polling.

**Neither will staffing agencies.** Net2Source, Ampstek, Yochana and the rest
post to Dice and job boards, not Greenhouse. Same aggregator leg picks them up.
That's roughly $30/month and it's what makes contract roles show up at all.

---

## 7. Stripe

```bash
export STRIPE_SECRET_KEY=sk_test_...
make stripe-setup          # creates products + prices, prints your .env lines
make stripe-listen         # local webhook forwarding → gives you whsec_...
python test_billing.py     # 15 tests, mocked Stripe, no network, no charges
```

`setup_stripe.py` is idempotent — it looks up products by `lookup_key` before
creating, so running it twice just prints the IDs again.

It creates:

| | |
|---|---|
| Product | CareerPilot Pro |
| Price | `$19.99/month` → `careerpilot_pro_monthly` |
| Price | `$191/year` → `careerpilot_pro_annual` |
| Portal | self-serve cancel at period end |

### Keys

| Key | Where it lives |
|---|---|
| `pk_test_…` publishable | frontend, safe to commit |
| `sk_test_…` secret | server `.env` only — **never** frontend, never a repo |
| `whsec_…` webhook | server `.env`, from `stripe listen` or the dashboard |

**If a secret key ever leaks** — a screenshot, a chat, a commit — roll it:
Dashboard → Developers → API keys → Roll key. Instant and free.

### Why the webhook signature check matters

`test_billing.py` proves it: an unsigned webhook claiming
`checkout.session.completed` is rejected and the account stays on `free`.
Without `stripe.Webhook.construct_event`, anyone who finds your endpoint
can POST themselves a Pro subscription.

Test cards: `4242 4242 4242 4242` succeeds · `4000 0000 0000 9995` declines ·
`4000 0025 0000 3155` triggers 3D Secure.

---

## 8. Getting to real volume

`ingest/run.py` is the pipeline. It targets **100+ live full-time and 200+
live contract** roles and tells you plainly when it's short.

```bash
make ingest-once     # one full pass across every source
make ingest-fast     # aggregators only — where new contract roles appear
make ingest-loop     # production: aggregators every 10 min, ATS every 2h
make board           # volume report against targets
```

### Sources — 379 company boards plus 6 aggregators

| Tier | Sources | Cost |
|---|---|---|
| ATS boards | Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Recruitee, Teamtailor, JazzHR, Breezy — 379 companies | **free, unlimited** |
| Free APIs | USAJobs, Remotive, RemoteOK, Arbeitnow | **free** |
| Free with key | Adzuna (1,000 calls/mo) | **free tier** |
| Metered | JSearch via RapidAPI | ~$30/mo |

Nothing scrapes. Every endpoint is a published API or public feed.

**Contract roles come almost entirely from the metered leg.** Staffing agencies
post to Dice and job boards, not to Greenhouse. Without `RAPIDAPI_KEY` your
contract count stays near zero — that $30/month is what makes the contract side
of the board exist at all.

### Why not poll everything every 5 minutes

It's the obvious idea and it backfires:

| | Requests/day | Outcome |
|---|---|---|
| Everything every 5 min | **115,200** | rate-limited in hours, IP-blocked in days, metered quota gone in an afternoon |
| Tiered (what's built) | **2,636** | new jobs surface in 10–20 min |

A company posts a job maybe twice a week. Polling its board 288 times a day
means 287 identical responses. The scheduler instead polls the ~15% of sources
that are actually active right now, and lets quiet boards drift to a 12-hour
cycle. Aggregators — scoped to `date_posted=today` — stay on a 10-minute cycle,
because that's where genuinely new postings appear first.

Sources promote and demote themselves: post something today and you move to the
warm tier; go quiet for a week and you drop to slow.

### Expected steady state

```
379 ATS boards, QA-filtered        ~57 full-time
USAJobs + Remotive + RemoteOK      ~40-80
JSearch, 8 queries daily           ~120-200 contract
Adzuna, 3 queries                  ~40-80
                                   ─────────────────
                                   250-400 live roles
```

Every posting is QA/SDET-filtered at ingest. A board of 400 relevant roles beats
one of 40,000 where a tester has to wade through sales listings — that's the
whole premise, so the filter is deliberately strict.

### Keeping it honest

- Anything not seen for 10 days is marked closed and disappears
- `seen_count` tracks reposts; 3+ shows a warning on the card
- Every job carries `first_seen`, so "posted 2 days ago" is real
- Dedup collapses the same role across sources into one fingerprint
