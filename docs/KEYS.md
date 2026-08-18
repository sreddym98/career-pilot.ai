# API keys — what you need and when

Verified against the code, not from memory. Grouped by what actually breaks
without each one.

---

## Zero keys — this already works

```bash
bash start.sh
```

- 379 company career boards (Greenhouse, Lever, Ashby, Workable, and five more)
- Remotive, RemoteOK, Arbeitnow
- **~100–140 live QA/SDET roles**
- Full profile, resume upload, job matching, application tracking

**No keys. No signup. No cost.** Enough to show people something real.

---

## The one that matters most

### `RAPIDAPI_KEY` — ~$30/mo

Without it your **contract count stays near zero**. Staffing agencies post to
Dice and job boards, not to company ATS — so no amount of free sources reaches
them. Adds **120–200 contract roles**.

Given your audience is staffing-agency contacts and contractors, this is the
difference between a board they'd use and one they wouldn't.

```
rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch → Subscribe → copy X-RapidAPI-Key
```

---

## Free, worth 15 minutes

| Key | Adds | Where |
|---|---|---|
| `USAJOBS_KEY` + `USAJOBS_EMAIL` | ~40–80 federal QA roles | developer.usajobs.gov/APIRequest |
| `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` | ~40–80 mixed roles | developer.adzuna.com |

Both free forever. Adzuna allows 1,000 calls/month, which is plenty at the
polling rate the scheduler uses.

**With all of the above: 250–400 live roles.** Past your 100 full-time /
200 contract targets.

---

## For the AI features

### `ANTHROPIC_API_KEY`

Gates resume tailoring and cover letters. Without it those return an error;
everything else works normally.

```
console.anthropic.com → API keys
```

Roughly **$0.06 per resume** (one call per role). The response cache means
regenerating the same resume for the same job costs nothing — that's what keeps
the $19.99 plan profitable.

---

## To take payments

Run this and it creates the products and prints two of the four:

```bash
export STRIPE_SECRET_KEY=sk_test_...
python setup_stripe.py
```

| Key | From |
|---|---|
| `STRIPE_SECRET_KEY` | dashboard.stripe.com → Developers → API keys |
| `STRIPE_PRICE_PRO_MONTHLY` | printed by `setup_stripe.py` |
| `STRIPE_PRICE_PRO_ANNUAL` | printed by `setup_stripe.py` |
| `STRIPE_WEBHOOK_SECRET` | `stripe listen --forward-to localhost:8000/api/billing/webhook` |

**The webhook secret is not optional.** Without it the signature check rejects
everything, so people pay and never get upgraded. `test_billing.py` proves both
directions: a valid webhook upgrades, a forged one is rejected.

---

## Before real users sign up

### `SUPABASE_JWT_SECRET` + `SUPABASE_URL` — free

Without these the API signs **everyone in as the same dev user**. Fine on your
laptop, unacceptable live — every visitor would share one profile.

```
supabase.com → new project → Settings → API → JWT Secret
```

### `FRONTEND_URL`

Your domain. CORS blocks the browser without it, and Stripe redirects land in
the wrong place.

---

## Genuinely optional

| Key | Why you might |
|---|---|
| `DATABASE_URL` | Falls back to SQLite. Switch to Postgres before you have real users. |
| `REDIS_URL` | Only matters past a few thousand concurrent users. |
| `STRIPE_PUBLISHABLE_KEY` | Only read by `/api/billing/config`. Safe to expose. |

---

## Order to do them in

| Stage | Keys | Cost | Result |
|---|---|---|---|
| **1. See it work** | none | $0 | ~100–140 live jobs |
| **2. Fill the board** | RAPIDAPI, USAJOBS, ADZUNA | $30/mo | **250–400 live jobs** |
| **3. Turn on AI** | ANTHROPIC | ~$0.06/resume | tailoring, cover letters |
| **4. Take money** | 4 × STRIPE | 2.9% + 30¢ | subscriptions |
| **5. Real accounts** | SUPABASE ×2, FRONTEND_URL, DATABASE_URL | $0–25/mo | multi-user, secure |

**Do stage 2 first.** A portal with 300 real jobs and no payments is worth
showing people. A portal with payments and 11 jobs isn't.

---

## Where they go

Everything server-side, in `be/.env` — never in `careerpilot.html`, never in a
repo. `.env.example` has every name with a comment.

The frontend needs exactly one setting, and it isn't a secret:

```js
const API_ENDPOINT = "https://api.yourdomain.com";
```

## If a key leaks

Rotate it. All three are instant and free:

- **Anthropic** — console.anthropic.com → API keys → revoke
- **Stripe** — Developers → API keys → Roll key
- **RapidAPI** — App dashboard → regenerate

Rotating is always cheaper than hoping nobody noticed.

---

## Profile evaluation ($5, one-time)

Uses the same `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` as the Pro
subscription, plus one more price:

```bash
python setup_stripe.py
# creates STRIPE_PRICE_EVAL alongside the Pro prices — copy it into .env
```

This is a one-time charge (`mode="payment"`), not a subscription, so it goes
through Stripe's `checkout.session.completed` event with `mode: "payment"`
rather than the subscription path. `test_evaluation.py` proves both directions:
a real payment unlocks the report, and a forged webhook does not.
