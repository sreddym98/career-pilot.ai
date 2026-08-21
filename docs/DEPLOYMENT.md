# Deployment Checklist

This is the release checklist for the current Career Pilot AI repository.

## Production topology

```text
Static frontend: https://app.your-domain.com
FastAPI API:     https://api.your-domain.com
Postgres:        managed production database
Ollama:          private API worker or replace with a managed model provider
```

Set the frontend API base to the deployed API URL before publishing the static site. Do not ship `http://localhost:8000` to customers.

## Required API environment

```env
ENV=prod
DATABASE_URL=postgresql+psycopg://...
FRONTEND_URL=https://app.your-domain.com
SUPABASE_URL=...
SUPABASE_JWT_SECRET=...
```

Use Supabase Auth or another production identity provider before inviting customers. The development user fallback is for local testing only.

## Real jobs

The direct ATS feed needs no provider keys. Run it every two hours:

```bash
PYTHONPATH=/app/server python /app/server/ingest/run.py --once --workers 20
```

Add these sources to reach broad volume beyond direct employer boards:

```env
USAJOBS_EMAIL=...
USAJOBS_KEY=...
ADZUNA_APP_ID=...
ADZUNA_APP_KEY=...
RAPIDAPI_KEY=...
```

Run the fast aggregation cycle every 10 minutes once the keys are configured:

```bash
PYTHONPATH=/app/server python /app/server/ingest/run.py --fast
```

Run the source verifier monthly and commit the updated catalog:

```bash
PYTHONPATH=/app/server python /app/server/ingest/verify_slugs.py --fix
```

## Gmail and phone verification

Follow [INTEGRATIONS.md](INTEGRATIONS.md). Configure Google OAuth and Twilio Verify in the API environment. Never place those secrets in the frontend.

## AI behavior

The app uses local Ollama when available and produces profile-grounded resume and interview material when inference is unavailable. For a public deployment, run Ollama behind private networking with resource limits, or replace `server/api/routers/ai.py` with a managed provider before promising higher throughput.

## Pre-release regression

```bash
cd server
python ingest/visa_parse.py
API=https://api.your-domain.com bash test_api.sh
python test_ai_resilience.py
python test_billing.py
python test_evaluation.py
python test_interview.py
python test_support.py
```

Browser acceptance checks:

1. Verify a real job card opens and its application link goes to the employer or ATS.
2. Build a resume, edit a bullet, download Word, and save the resume-only PDF.
3. Generate a mock interview with a job description and inspect the technical and behavioral sections.
4. Confirm Gmail and phone setup show Done only after provider verification.
5. Confirm email fallback offers copy/drag-in instructions when no desktop mail client exists.
6. Complete Stripe test checkout and verify the webhook changes the plan only after signature validation.

## Operational safeguards

- Keep Google, Twilio, Stripe, database, and job-provider keys only in the deployment secret manager.
- Back up the production database before running schema migrations.
- Monitor job-ingestion error counts and active-job volume daily.
- Do not claim an application was sent unless the final delivery provider confirms it.
