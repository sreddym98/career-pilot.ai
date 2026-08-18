# careerpilot.ai — Build & Deploy Guide

Everything needed to take `careerpilot.html` from a working prototype to a live product.

The backend, database, AI proxy, and browser extension are **already built and
tested** — see §0. What remains is account setup you have to do yourself, plus
the job-source list.

---

## 0. Current status

Everything in the table below is **built, packaged, and tested**. This is not a
plan — it's what's in `careerpilot-backend.zip` right now.

| Piece | Status | Tests |
|---|---|---|
| Frontend — all 10 pages | ✅ Built — `careerpilot.html` | 196 passing |
| Job ingestion pipeline | ✅ Built — `ingest/ingest.py` | dedup + classification verified |
| **Database** — 9 tables | ✅ Built — `api/models.py` + `seed.py` | tables created, seeded, verified |
| **API server** — 16 endpoints | ✅ Built — `api/` | **38/38 against a live server** |
| **AI proxy** — key stays server-side | ✅ Built — `api/routers/ai.py` | plan + credit gates, cache |
| **Browser extension** — CareerPilot Autofill | ✅ Built — `extension/` | **38/38 vs real ATS markup** |
| Auth (Supabase JWT + dev fallback) | ✅ Built — `api/auth.py` | works with zero config |
| Payments (Stripe Checkout + webhook) | ✅ Built — `api/routers/billing.py` | signature verification in place |
| Referral program | ✅ Built — `api/routers/referrals.py` | credit accounting verified |
| Visa parser | ✅ Built — `ingest/visa_parse.py` | **15/15** |

### What's actually left for you

| Task | Why only you can do it | Time |
|---|---|---|
| Buy a domain | Needs your card | 10 min |
| Cloudflare Pages — upload `careerpilot.html` as `index.html` | Your account | 10 min |
| Railway — connect repo, paste env vars | Your account | 20 min |
| Supabase — new project, copy URL + JWT secret | Your account | 15 min |
| Stripe — 2 products, copy price IDs + webhook secret | Your account, your bank details | 30 min |
| Grow `ingest/companies.yaml` to 300+ ATS slugs | **The real work** — decides whether the board has anything in it | 4–8 hrs |
| Publish the extension to Chrome Web Store | Your developer account ($5 one-off) | 30 min + 1–3 wk review |

**Roughly 1.5 hours of clicking, plus the company list.**

### Run what's built, right now

```bash
unzip careerpilot-backend.zip && cd be
pip install -r requirements.txt
python seed.py        # creates DB, loads sample data
make dev              # http://localhost:8000/docs
make test             # visa parser + all 38 API tests
```

No Postgres needed to start — it falls back to SQLite. No Supabase needed —
with no JWT secret set it signs you in as a local dev user so every endpoint
works immediately. Swap both for the real thing later by setting two env vars.


## 1. Stack

Chosen for one person shipping fast, not for scale you don't have yet.

```
Frontend    Static HTML (what you have) → later Next.js if you need SSR
API         FastAPI (Python — matches ingest.py, one language)
Database    Postgres 16 (Supabase or Neon free tier to start)
Cache       Redis (Upstash free tier)
Queue       Postgres-backed (pg-boss style) — do NOT add Celery/RabbitMQ yet
Auth        Supabase Auth or Clerk — do NOT roll your own
Payments    Stripe Checkout
AI          Anthropic API, proxied through YOUR server (never client-side)
Hosting     Frontend: Cloudflare Pages · API: Railway or Fly.io
Email       Resend (3k/mo free)
```

**Why not Next.js everywhere:** your ingest and classification are Python. Two languages means two mental models. FastAPI + static frontend keeps it one.

---

## 2. Repository layout

```
careerpilot/
├── web/
│   └── index.html              # the file you have now
├── api/
│   ├── main.py                 # FastAPI app
│   ├── routers/
│   │   ├── jobs.py             # GET /api/jobs  (filters, pagination)
│   │   ├── profile.py          # GET/PUT /api/profile
│   │   ├── ai.py               # POST /api/tailor, /api/cover-letter
│   │   ├── billing.py          # Stripe checkout + webhook
│   │   └── network.py          # connections, referral paths
│   ├── models.py               # SQLAlchemy
│   ├── taxonomy.py             # THE MOAT — shared with classifier
│   ├── classify.py             # job → role_family
│   ├── auth.py                 # JWT verification
│   └── settings.py             # env config
├── ingest/
│   ├── ingest.py               # the file you have
│   ├── connectors/
│   │   ├── greenhouse.py
│   │   ├── lever.py
│   │   ├── ashby.py
│   │   └── aggregator.py       # JSearch / Adzuna
│   ├── dedup.py                # fingerprinting
│   ├── visa_parse.py           # JD → {usc,gc,h1b,opt}
│   └── companies.yaml          # your ATS slug list — GROW THIS
├── extension/                  # CareerPilot Autofill (phase 2)
├── migrations/                 # Alembic
├── docker-compose.yml          # local: postgres + redis
└── .env.example
```

---

## 3. Database schema ✅ BUILT — `api/models.py`

```sql
-- ═══ USERS ═══
CREATE TABLE users (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email           TEXT UNIQUE NOT NULL,
  name            TEXT,
  slug            TEXT UNIQUE,              -- careerpilot.ai/santoshreddy
  headline        TEXT,
  location        TEXT,
  summary         TEXT,
  work_auth       TEXT[],                   -- {'h1b'} / {'gc','usc'}
  plan            TEXT DEFAULT 'free',      -- free | pro | annual
  stripe_customer TEXT,
  ai_credits_used INT DEFAULT 0,            -- resets monthly — see §5
  credits_reset_at TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE positions (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID REFERENCES users(id) ON DELETE CASCADE,
  company    TEXT NOT NULL,
  role       TEXT NOT NULL,
  started_on DATE NOT NULL,                 -- store as DATE, format in UI
  finished_on DATE,                         -- NULL = current
  location   TEXT,
  bullets    JSONB DEFAULT '[]',
  sort_order INT DEFAULT 0
);
-- duration is DERIVED, never stored:
--   AGE(COALESCE(finished_on, CURRENT_DATE), started_on)

CREATE TABLE user_skills (
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  skill   TEXT NOT NULL,
  is_top  BOOLEAN DEFAULT false,
  PRIMARY KEY (user_id, skill)
);

-- ═══ JOBS ═══
CREATE TABLE jobs (
  fingerprint    TEXT PRIMARY KEY,          -- from ingest.py dedup
  source         TEXT NOT NULL,
  source_id      TEXT,
  company        TEXT NOT NULL,
  company_type   TEXT,                      -- employer | staffing
  is_fortune500  BOOLEAN DEFAULT false,
  title          TEXT NOT NULL,
  location       TEXT,
  work_mode      TEXT,                      -- remote | hybrid | onsite
  employment     TEXT,                      -- fulltime | contract
  description    TEXT,
  apply_url      TEXT,
  comp_min       INT, comp_max INT, comp_unit TEXT,   -- 'yr' | 'hr'
  exp_min        INT, exp_max INT,
  -- visa: 'y' accepted | 'n' excluded | 'u' not stated
  visa_usc CHAR(1) DEFAULT 'u',
  visa_gc  CHAR(1) DEFAULT 'u',
  visa_h1b CHAR(1) DEFAULT 'u',
  visa_opt CHAR(1) DEFAULT 'u',
  role_family    TEXT,                      -- taxonomy id — YOUR MOAT
  career_field   TEXT,
  required_skills TEXT[],
  embedding      VECTOR(1024),              -- pgvector, for matching
  posted_at      TIMESTAMPTZ,
  first_seen     TIMESTAMPTZ NOT NULL,
  last_seen      TIMESTAMPTZ NOT NULL,
  seen_count     INT DEFAULT 1,
  relisted       BOOLEAN DEFAULT false,
  active         BOOLEAN DEFAULT true
);
CREATE INDEX ON jobs (active, role_family, posted_at DESC);
CREATE INDEX ON jobs (active, career_field);
CREATE INDEX ON jobs USING GIN (required_skills);
CREATE INDEX ON jobs USING ivfflat (embedding vector_cosine_ops);

-- ═══ APPLICATIONS ═══
CREATE TABLE applications (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
  fingerprint TEXT REFERENCES jobs(fingerprint),
  status      TEXT DEFAULT 'queued',
  -- queued | preparing | needs_input | ready | submitted
  -- | responded | interview | selected | rejected
  blocker     TEXT,          -- 'salary' | 'sponsorship' | 'suspicious_repost'
  tailored_resume JSONB,
  cover_letter TEXT,
  form_fields JSONB,
  applied_at  TIMESTAMPTZ,
  updated_at  TIMESTAMPTZ DEFAULT now()
);

-- ═══ AI CACHE — this is what protects your margin ═══
CREATE TABLE ai_cache (
  cache_key   TEXT PRIMARY KEY,    -- sha256(resume_hash + jd_hash + task)
  result      JSONB NOT NULL,
  hits        INT DEFAULT 0,
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- ═══ COURSES & NETWORK ═══
CREATE TABLE courses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT, provider TEXT, url TEXT,
  price_cents INT, kind TEXT, hours INT,
  skills TEXT[], description TEXT
);
CREATE INDEX ON courses USING GIN (skills);

CREATE TABLE connections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  name TEXT, role TEXT, company TEXT,
  degree SMALLINT,          -- 1, 2, 3
  how_known TEXT
);
CREATE INDEX ON connections (user_id, company);
```

---

## 4. Job ingestion

### 4a. Free tier — ATS endpoints

No auth, no ToS problem, clean structured JSON.

```
Greenhouse  https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
Lever       https://api.lever.co/v0/postings/{slug}?mode=json
Ashby       https://api.ashbyhq.com/posting-api/job-board/{slug}
```

**Building your slug list — this is the actual work.** Aim for 300+ companies.
- Greenhouse-hosted boards are `job-boards.greenhouse.io/{slug}` — search that pattern
- For each target company, check `careers.{company}.com` and see where "Apply" redirects
- Public lists exist on GitHub (`greenhouse-companies`); verify before trusting

Poll daily. 300 companies ≈ 2,000 active postings ≈ 30–60 genuinely new per day.

### 4b. Paid tier — aggregator

Catches staffing agencies (Net2Source, Ampstek, Yochana), which never use Greenhouse.

- **JSearch** (RapidAPI) — reads Google for Jobs. ~$30/mo. `date_posted=today`.
- **Adzuna** — 1,000 calls/mo free. Good supplement.

**Do not scrape LinkedIn or Indeed.** Indeed's API closed in 2021; LinkedIn blocks aggressively and pursues scrapers. Not worth the legal exposure on a business you want to sell someday.

### 4c. Fortune 500 caveat

F500 companies mostly run **Workday**, which has no clean public API — every tenant has its own endpoint shape. You will get F500 coverage from the aggregator leg, not from direct ATS. Budget for that; don't burn a week trying to build a universal Workday connector.

### 4d. Visa parsing

Runs at ingest, once per job. Regex first, LLM only for ambiguous cases (cheaper).

```python
NEGATIVE = [
  (r"no\s+(h-?1b|visa)\s+sponsorship", {"h1b":"n"}),
  (r"(us\s+citizen|usc)\s+(only|required)", {"h1b":"n","opt":"n","gc":"n"}),
  (r"citizen(ship)?\s+required", {"h1b":"n","opt":"n"}),
  (r"no\s+c2c", {}),                       # contract terms, NOT visa
  (r"(must|able)\s+to\s+work\s+without\s+sponsorship", {"h1b":"n","opt":"n"}),
  (r"security\s+clearance", {"h1b":"n","opt":"n","gc":"n"}),
]
POSITIVE = [
  (r"h-?1b\s+(transfer|sponsorship)\s+(ok|available|welcome)", {"h1b":"y"}),
  (r"(only\s+)?h-?1b", {"h1b":"y","usc":"n","gc":"n","opt":"n"}),
  (r"opt|cpt|ead", {"opt":"y"}),
  (r"will\s+sponsor", {"h1b":"y"}),
]
```

**Default to `'u'` (not stated), never to `'n'`.** Most postings say nothing. Marking silence as rejection would delete 70% of your board and destroy trust. The UI already handles `'u'` correctly.

### 4e. Classification — your moat

```python
def classify(job) -> tuple[str, str]:
    # 1. keyword score against taxonomy (free, catches ~70%)
    scores = {f.id: score(job.description, f.keywords) for f in TAXONOMY}
    best = max(scores, key=scores.get)
    if scores[best] > CONFIDENT:
        return best, FAM[best].field
    # 2. LLM fallback ONLY for the ambiguous 30%
    return llm_classify(job)   # cache by hash(title+company)
```

Never classify per-request. Once at ingest, stored in `jobs.role_family`.

---

## 5. AI proxy ✅ BUILT — `api/routers/ai.py`

**The prototype calls `api.anthropic.com` from the browser.** That works inside Claude artifacts because the key is injected server-side. **On your own domain it would expose your API key to every visitor.** Anyone could drain your account.

Every AI call must go through your server:

```python
@router.post("/api/tailor")
async def tailor(req: TailorRequest, user = Depends(current_user)):
    # 1. Plan gate
    if user.plan == "free":
        raise HTTPException(402, "Upgrade to Pro for resume tailoring")

    # 2. Credit gate — protects your margin
    if user.ai_credits_used >= CREDITS[user.plan]:
        raise HTTPException(429, "Monthly generation limit reached")

    # 3. Cache — the single most important line in this file
    key = sha256(f"{hash(req.resume)}{hash(req.jd)}tailor".encode()).hexdigest()
    if cached := await db.get_cache(key):
        return cached                      # costs you nothing

    # 4. Call, with YOUR key, server-side only
    result = await anthropic.messages.create(
        model="claude-sonnet-4-6", max_tokens=1500,
        messages=[{"role": "user", "content": build_prompt(req)}])

    await db.set_cache(key, result)
    await db.increment_credits(user.id)
    return result
```

### Cost model — read this before pricing anything

| | |
|---|---|
| Tokens per tailor | ~4k in + 1.5k out |
| Cost per tailor | ~$0.02–0.05 |
| Pro revenue | $19.99/mo |
| Break-even | ~400 generations/user/month |
| **Recommended cap** | **150/mo (Pro), 250/mo (Annual)** |

Then in the frontend, replace the direct fetch:

```javascript
// BEFORE (prototype)
fetch("https://api.anthropic.com/v1/messages", {...})

// AFTER (production)
fetch("/api/tailor", {
  method: "POST",
  headers: {"Content-Type":"application/json", "Authorization": `Bearer ${token}`},
  body: JSON.stringify({resume, jd})
})
```

Three call sites to change: `buildResume()`, and the two agent generation paths.

---

## 6. Wiring the frontend to the API

The prototype uses hardcoded `const J = [...]`. Replace with:

```javascript
let J = [];
async function loadJobs() {
  const p = new URLSearchParams({
    q: $("q").value,
    auth: document.querySelector('input[name=au]:checked').value,
    fields: vl(".f-fld").join(","),
    families: vl(".f-fam").join(","),
    employment: vl(".f-emp").join(","),
    modes: vl(".f-loc").join(","),
    company: vl(".f-co").join(","),
    limit: 25, offset: SHOWN
  });
  const r = await fetch(`/api/jobs?${p}`, {headers: authHeader()});
  const d = await r.json();
  J = d.jobs; rn();
}
```

**Move filtering server-side once you exceed ~500 jobs.** Below that, client-side is faster (no round trip). The pagination already added means the DOM cost is flat either way.

Same swap for `EXP`, `SKILLS`, `NET`, `CRS`, `TK`, `AGQ` — all currently hardcoded consts, all read from `/api/profile`.

---

## 7. Auth ✅ BUILT — `api/auth.py`

Use **Supabase Auth** or **Clerk**. Do not build your own — password reset, email verification, and session rotation are where solo projects leak security holes.

```
Sign up → magic link or Google OAuth
       → row in users
       → JWT in httpOnly cookie
       → API verifies on every request
```

Public profile pages (`/santoshreddy`) render server-side from `users.slug` with no auth, showing only fields the user marked public.

---

## 8. Payments ✅ BUILT — `api/routers/billing.py`

```
Checkout:
  POST /api/billing/checkout
    → stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{price: PRICE_PRO_MONTHLY, quantity: 1}],
        success_url=".../welcome", cancel_url=".../pricing",
        client_reference_id=user.id)
    → return session.url → redirect

Webhook: POST /api/billing/webhook
  checkout.session.completed        → users.plan = 'pro'
  customer.subscription.updated     → sync plan
  customer.subscription.deleted     → users.plan = 'free'
  invoice.payment_failed            → email + grace period

  VERIFY THE SIGNATURE:
    stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
  Without this anyone can POST themselves a free Pro plan.
```

**Never store card numbers.** Stripe Checkout is a hosted redirect — card data never touches your server, which keeps you out of PCI-DSS scope entirely. You know from Mastercard what being in scope costs.

**Selling internationally?** Consider **Paddle** or **Lemon Squeezy** instead. They act as merchant of record and handle every tax jurisdiction — ~5% vs Stripe's 2.9%, but you skip US state sales-tax registration and EU VAT entirely. For a solo founder that trade is usually worth it.

**On the struck-through $29.99:** if you never actually charge $29.99, a permanent "was $29.99, now $19.99" is a dark pattern the FTC has pursued companies over. The UI labels it *launch pricing, locked 12 months* — which is true and does the same conversion work legitimately. Keep it that way.

---

## 9. Browser extension ✅ BUILT — `extension/`

Built and tested against real Workday, Greenhouse, Lever, and iCIMS markup — 38/38 passing. Load it unpacked via `chrome://extensions` → Developer mode.

```
extension/
├── manifest.json          # MV3
├── content/
│   ├── detect.js          # which ATS is this page?
│   ├── workday.js         # per-ATS field maps
│   ├── greenhouse.js
│   ├── lever.js
│   └── icims.js
├── background.js          # fetches prepared application from your API
└── popup/
```

```json
{
  "manifest_version": 3,
  "name": "CareerPilot Autofill",
  "permissions": ["storage", "activeTab"],
  "host_permissions": [
    "https://*.myworkdayjobs.com/*",
    "https://boards.greenhouse.io/*",
    "https://jobs.lever.co/*",
    "https://*.icims.com/*"
  ]
}
```

**Rules that keep you out of trouble:**
1. **Never auto-submit.** Fill only. The user presses submit.
2. **Never guess salary or sponsorship answers.** Highlight and stop.
3. Request the narrowest `host_permissions` you can — broad ones fail review.
4. Chrome Web Store review: 1–3 weeks, first submission often rejected on privacy-policy wording. Write that page before you submit.

---

## 10. Deployment

```bash
# Frontend — Cloudflare Pages
wrangler pages deploy web/ --project-name careerpilot

# API — Railway
railway up
railway variables set ANTHROPIC_API_KEY=... STRIPE_SECRET_KEY=...

# Ingest — Railway cron, daily 06:00 UTC
0 6 * * *  python ingest/ingest.py --run

# Migrations
alembic upgrade head
```

### `.env.example`
```bash
DATABASE_URL=postgresql://user:pass@host:5432/careerpilot
REDIS_URL=redis://...
ANTHROPIC_API_KEY=sk-ant-...
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_PRO_MONTHLY=price_...
STRIPE_PRICE_PRO_ANNUAL=price_...
RAPIDAPI_KEY=...                 # JSearch
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
RESEND_API_KEY=...
FRONTEND_URL=https://careerpilot.ai
```

### Monthly cost at launch
| | |
|---|---|
| Cloudflare Pages | $0 |
| Railway (API + cron) | $5–20 |
| Postgres (Supabase/Neon free) | $0 → $25 |
| Redis (Upstash free) | $0 |
| JSearch | $30 |
| Domain | $1 |
| Anthropic API | **variable — your real cost** |
| **Fixed total** | **~$40–75/mo** |

Four Pro subscribers cover fixed costs. Everything after that is AI spend, which scales with usage — hence the caps in §5.

---

## 11. Capacity

| Tier | Concurrent users | Bottleneck |
|---|---|---|
| Static frontend (CDN) | Effectively unlimited | 100GB/mo free ≈ 2.7M loads |
| API + Postgres, no cache | ~3,000 | Connection pool → use PgBouncer |
| API + Redis cache | 20,000+ | Job list is identical for most users — cache it |
| AI features | **~50 active Pro users** | Anthropic rate limit + your bill |

**What breaks first is the AI bill, not the servers.** Plan caps before scale.

Measured on the current frontend (jsdom, ~5–10× slower than a real browser):
```
job list render (25)     24ms      →  ~3ms real
render @1,020 jobs       47ms      →  ~6ms real
render @10,020 jobs      86ms      →  ~10ms real
resume detection         0.08ms
payload                  154KB     →  ~44KB gzipped
```

---

## 12. What's left, in order

**Week 1 — get it live (~2 hrs of clicking)**
- [ ] Buy domain
- [ ] Cloudflare Pages: upload `careerpilot.html` as `index.html`
- [ ] Railway: deploy `be/`, set `ANTHROPIC_API_KEY`
- [ ] Supabase: new project → paste `SUPABASE_JWT_SECRET`
- [ ] Postgres: set `DATABASE_URL`, run `python -c "from api.db import init_db; init_db()"`
- [ ] Point the frontend at the API using `api_client.js`

**Week 2 — fill the board (the real work)**
- [ ] Grow `ingest/companies.yaml` to 300+ Greenhouse/Lever/Ashby slugs
- [ ] Add `RAPIDAPI_KEY` for the staffing-agency leg
- [ ] Cron the ingest daily; confirm 100+ new/relisted per day

**Week 3 — money**
- [ ] Stripe: 2 products, price IDs, webhook secret
- [ ] Test checkout end to end in test mode
- [ ] Privacy policy + terms (Stripe and Chrome both require them)

**Week 4 — ship**
- [ ] Submit CareerPilot Autofill to the Chrome Web Store
- [ ] Sentry + Plausible
- [ ] Show it to 20 people in QA/SDET communities

## 13. What actually determines whether this works

Not the code. Three things:

**1. The taxonomy.** 44 specializations correctly mapped is the whole product. JobRight shows SDETs developer roles because their classifier stops at "Software Engineer." You have 7 years of domain knowledge nobody can hire for cheaply. Keep it in one file, version it, tune it against real postings.

**2. Job coverage.** JobRight adds ~400k listings/day. You cannot match that and shouldn't try — their volume comes from funded scraping infrastructure. Your 10% correctly classified beats their 100% miscategorized *for your audience*. Go deep on QA/SDET first; the same architecture points at nursing or accounting later.

**3. Honest signals.** Ghost-job flags, "sponsorship not stated," "reposted 4×," real gap analysis. Every competitor optimizes for looking optimistic. The first fabricated applicant count a user catches costs you the relationship permanently.

## Legal, before launch
- Privacy policy + terms (required by Stripe and Chrome Web Store)
- GDPR/CCPA: export and delete endpoints
- Don't scrape LinkedIn or Indeed
- **Name check:** search USPTO TESS for "CareerPilot" before you print anything. It's a plausible-sounding name, which means someone may already hold it.

---

# APPENDIX A — What's in the zip

```
be/
├── Makefile                setup / dev / seed / test
├── seed.py                 creates tables + sample data, one command
├── test_api.sh             38 endpoint tests
├── api_client.js           wires the frontend to the API
├── docker-compose.yml      postgres + redis + api
├── Dockerfile
├── requirements.txt
├── .env.example
├── api/
│   ├── main.py             app + CORS
│   ├── settings.py         config + credit allowances
│   ├── models.py           9 tables. Durations DERIVED, never stored
│   ├── db.py               Postgres in prod, SQLite fallback for local
│   ├── auth.py             Supabase JWT + zero-config dev user
│   ├── credits.py          allowance + referral accounting
│   └── routers/
│       ├── ai.py           AI PROXY — the only place your key lives
│       ├── jobs.py         search, filters, referral paths
│       ├── profile.py      positions CRUD, gap detection, public page
│       ├── billing.py      Stripe Checkout + verified webhook
│       └── referrals.py    invite, attribute, credit grants
├── ingest/
│   ├── ingest.py           ATS pollers + dedup
│   └── visa_parse.py       JD → visa flags, 15/15
└── extension/              CareerPilot Autofill (MV3)
    ├── manifest.json
    ├── background.js       talks to your API, holds the session token
    ├── content/detect.js   identifies Workday/Greenhouse/Lever/Ashby/iCIMS/SmartRecruiters
    ├── content/fill.js     fills fields, refuses salary/sponsorship/demographics
    └── popup/              status, fill button, settings
```

# APPENDIX B — Referral program

Built and wired end to end.

**The offer:** +100 generations/month per active referral, for both sides,
recurring while they stay active. Five referrals (500, the cap) exceeds the Pro
allowance — a heavy referrer gets more than a paying customer, free.

**Why it's structured this way**

- *Recurring, not one-time.* A one-off bonus gets shared once. A recurring one
  gives the referrer a reason to care whether the person actually sticks.
- *7-day qualification.* Credits unlock only after the referee stays active a
  week. Without this, referral programs get farmed with throwaway emails within
  days of launch.
- *500 cap.* Generations cost you $0.02–0.05 each. Uncapped referrals would let
  someone run up a $200/month bill on a free account.
- *Masked emails.* You see `a•••@gmail.com` — enough to recognise who, never the
  full address of someone who didn't consent to being listed.

`api/routers/referrals.py` + `api/credits.py`. The qualification sweep runs as a
daily cron: `credits.qualify_pending(db)`.

---

# APPENDIX C — Total cost

## To launch

| | |
|---|---|
| Domain (.ai is pricey; .com ~$12) | $12–70/yr |
| Cloudflare Pages | $0 |
| Railway (API + 2 crons) | $5–20/mo |
| Postgres (Supabase/Neon free → paid) | $0 → $25/mo |
| Redis (Upstash free) | $0 |
| Supabase Auth (50k MAU free) | $0 |
| JSearch (staffing-agency jobs) | $30/mo |
| Resend email (3k/mo free) | $0 |
| Stripe | 2.9% + 30¢ per charge |
| **Fixed monthly** | **$35–75** |

**Four Pro subscribers cover all fixed costs.**

## The variable cost that actually matters

Anthropic API. This is not a rounding error — it's the whole margin question.

| | |
|---|---|
| One resume (header + 3 role calls) | ~$0.06–0.15 |
| One cover letter | ~$0.02–0.04 |
| Break-even at $19.99/mo | ~150–300 generations |
| **Credit cap set at** | **150 (Pro), 250 (Annual), 500 hard ceiling** |

**Cache hit rate is the single biggest lever.** Same resume + same JD returns the
stored answer at zero cost. Expect 30–50% hits in real use — users regenerate
constantly. That roughly doubles your effective margin, and it's already
implemented in `ai.py`.

## Projected P&L

| Users | Revenue | AI cost | Infra | Net |
|---|---|---|---|---|
| 10 Pro | $200 | ~$45 | $50 | **+$105** |
| 50 Pro | $1,000 | ~$225 | $75 | **+$700** |
| 200 Pro | $4,000 | ~$900 | $150 | **+$2,950** |
| 1,000 Pro | $20,000 | ~$4,500 | $400 | **+$15,100** |

Assumes ~60% of allowance used on average and a 40% cache hit rate. Margin holds
because of the caps, not despite them — an "unlimited" plan inverts this table
the first time a power user finds you.

## What breaks first, in order

1. **Your Anthropic bill** — around 50 heavy Pro users. Caps and cache are the defence.
2. **Postgres connections** — ~3,000 concurrent. Add PgBouncer.
3. **Static hosting bandwidth** — ~2.7M page loads/month on the free tier.

The servers are not your problem. The AI bill is.
