# careerpilot.ai

Job search built for US tech workers who need visa clarity.

**Private and proprietary.** See [LICENSE](LICENSE).

---

## What it is

A job portal that filters on the things that actually decide whether you can
get a role — work authorization, experience level, and specialization — rather
than keyword-matching job titles.

| | |
|---|---|
| **Visa-first** | Every posting shows whether it's open to USC / GC / H1B / OPT. Postings that exclude you are hidden, not buried. |
| **Real specializations** | 27 testing and engineering specializations, not "Software Developer". An SDET stops seeing backend roles. |
| **Resume is the profile** | One upload — PDF, Word, or text — extracts roles, dates, bullets, and skills. |
| **Honest signals** | Repost counts, days live, employment gaps on your own profile, and gaps in your fit for each role. |
| **AI that cuts** | Resume tailoring removes bullets that dilute you for a specific role, and says what it dropped. |

---

## Layout

```
web/          index.html — the entire frontend, one file, no build step
server/       FastAPI API, ingest pipeline, Stripe, auth
extension/    CareerPilot Autofill (Chrome MV3)
scripts/      secret scanner, git hooks
docs/         setup, keys, go-live
```

---

## Run it

```bash
bash scripts/setup-hooks.sh     # once — blocks secrets from being committed
cd server && bash start.sh      # installs, seeds, pulls real jobs, starts API
```

Then set one line in `web/index.html`:

```js
const API_ENDPOINT = "http://localhost:8000";
```

Open `web/index.html`. Done.

**With no API keys at all** you get ~100–140 live QA/SDET roles from 379
company career boards plus free public APIs. See [docs/KEYS.md](docs/KEYS.md)
for what each optional key adds.

---

## Tests

```bash
cd server
make test                        # API (38) + visa parser (15)
python test_billing.py           # Stripe, mocked — 15
python test_ai_resilience.py     # upstream failure handling — 14
```

---

## Docs

- [docs/KEYS.md](docs/KEYS.md) — every API key, what breaks without it, cost
- [docs/GO_LIVE.md](docs/GO_LIVE.md) — deployment and pre-launch checklist
- [docs/SETUP.md](docs/SETUP.md) — architecture and build guide
- [docs/GITHUB.md](docs/GITHUB.md) — pushing this repo
- [SECURITY.md](SECURITY.md) — secret handling

---

## Before you make this public

Don't, without changing the license. But if you ever do:

- Rotate every key that has ever been in a `.env` on any machine
- Check the full git history with `bash scripts/check-secrets.sh --all`
- Search USPTO TESS for "CareerPilot" before using the name commercially

---

## Profile evaluation

A $5 one-time onboarding product, separate from the Pro subscription. Collects
career goals, then scores the person's resume, experience, and visa status
against their stated target — with an honest readiness score and concrete
next steps, not generic advice.

`server/api/routers/evaluation.py` — payment-gated: the report is generated
only after a webhook confirms payment, never before. `test_evaluation.py`
proves a forged webhook cannot unlock it (18/18).
