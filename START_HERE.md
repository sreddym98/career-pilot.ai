# careerpilot.ai — start here

If a friend sent you this repo to help out, read this file first. It's the map — everything else in here is a room you can go into once you know which one you need.

---

## What this actually is

A job search platform for US tech workers, with visa clarity built into the core (not bolted on) — and a separate mode for staffing recruiters managing a bench of candidates.

**It is not an idea or a mockup. It's a working product** that currently runs in demo mode because it isn't connected to real accounts, real payments, or a live job feed yet. Every screen you click through actually works — it's just showing sample data and telling you honestly when it can't do something for real (e.g. "Demo mode — nothing was actually sent").

## Try it right now, no setup

Open **`web/index.html`** in any browser. That's the whole frontend — one file, nothing to install. Click around. Upload a fake resume. Try the recruiter mode toggle in the sidebar. Everything you see is real, working UI — it's the *data* behind it that's sample until the backend is connected.

## What's built vs. what's missing

**Built and tested (681+ automated tests passing):**
- Full job-seeker experience: search, visa-aware filtering, AI resume tailoring, cover letters, application tracking, Autopilot (prepares applications on a schedule, you approve — never sends blind), mock interview practice, profile evaluation ($5 one-time)
- Full recruiter experience: candidate bench, fit-matched job ranking, submission tracking
- Real billing structure: Free / Pro (with 1/3/6-month pricing) / Recruiter / Enterprise
- A support ticket system with real priority routing for paying customers
- A Chrome extension that autofills job applications
- A backend job-ingest pipeline that pulls from 379+ real company career sites plus aggregator APIs

**Missing — this is the actual help-wanted list:**
- The backend isn't deployed anywhere yet (it runs locally, needs a real host)
- No Stripe account is connected, so no real payments happen yet
- No AI API key is wired in yet, so tailoring/evaluation/interview features run in a demo fallback
- `support@careerpilot.ai` isn't a real inbox yet
- No privacy policy or terms of service exist yet (required before Stripe or the Chrome extension can go live)
- No one's done a trademark check on the name "careerpilot"

None of these are hard, individually. They're just tasks, and they're listed below by rough skill needed so you can pick the one that fits whoever's helping.

---

## Tasks, by what kind of help you have

### "I know how to deploy a backend" → 30–60 minutes
Read **`docs/GO_LIVE.md`**. Deploy `server/` to Railway, Render, or Fly.io (all have free tiers to start). Then in `web/index.html`, find this line near the top of the `<script>` block and point it at the real backend URL:
```js
const API_ENDPOINT = "";
```
That single line is the entire switch from demo mode to live.

### "I can set up Stripe" → 20 minutes
Read **`docs/KEYS.md`**, the Stripe section. Create a Stripe account, get the secret key, run `python setup_stripe.py` from inside `server/` — it auto-creates every price tier (Pro monthly/3-month/6-month, Recruiter, the $5 evaluation) and prints the IDs to paste into your environment. No manual price creation needed.

### "I can get an Anthropic API key" → 10 minutes
Sign up at console.anthropic.com, generate a key, set it as `ANTHROPIC_API_KEY`. This single key turns on resume tailoring, cover letters, the $5 evaluation, and mock interview generation — they all share it.

### "I'm good at legal/admin stuff" → a few hours
- Draft a privacy policy and terms of service (required before Stripe processes real payments, and before the Chrome extension can be submitted for review)
- Do a quick USPTO trademark search on "careerpilot" to make sure the name is clear
- Set up `support@careerpilot.ai` as a real inbox (Google Workspace, or any email host)

### "I can review code / find bugs" → any amount of time
Every feature has a matching test. Backend: `test_*.py` in `server/`. Frontend: `web/tests/` — 21 files, 626 tests, run them all with `npm install && bash run-all.sh` from inside that folder. Read `web/tests/README.md` for what each one covers, and `SECURITY.md` for what's already been checked. `/api/support/queue` in `server/api/routers/support.py` is intentionally left without an admin check right now — that's the one known thing that must be locked down before this goes live, so anyone touching auth should look there first.

### "I just want to poke at it and give feedback" → 15 minutes
Open `web/index.html`, try both modes (there's a toggle top of the sidebar), try uploading a resume, try the evaluation and mock interview features. Tell whoever's running this what's confusing or what breaks.

---

## If you get stuck

- **General setup**: `docs/SETUP.md` — the long, thorough version of all of this
- **Just the API keys and what each one unlocks**: `docs/KEYS.md`
- **Pushing changes to GitHub**: `docs/GITHUB.md`
- **The Chrome extension specifically**: `docs/EXTENSION.md`
- **What's already been secured / what to check**: `SECURITY.md`

This repo is private and proprietary — see `LICENSE`. If you're reading this, you were given access on purpose.
