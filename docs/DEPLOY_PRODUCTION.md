# Production deploy (free tier, browser only)

Stack: Cloudflare Pages (site) + Render (API) + Neon (Postgres) + GitHub Actions (cron) + Resend (email).
Do the steps in order. Keep a scratch note of each value you generate; never paste secrets into the repo.

## 1. Generate secrets
Run in any Python (or an online-free Colab notebook):

| Name | Command |
|---|---|
| `AUTH_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `CRON_SECRET` | same command, a different value |
| `INTEGRATION_ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

## 2. Neon (database)
1. neon.tech > sign up > **Create project** (region near Render's, e.g. US East).
2. Dashboard > **Connect** > copy the connection string. Change the start to `postgresql+psycopg://` if it says `postgresql://`. Keep `?sslmode=require`.
3. This is `DATABASE_URL`. Tables are created automatically on first start.

## 3. Render (API)
1. render.com > **New > Blueprint** > connect GitHub > pick this repo (it reads `render.yaml`).
2. Fill the prompted variables (table in section 10). Leave optional ones blank for now; add later under **Environment**.
3. Apply. First build takes a few minutes. Open `https://<service>.onrender.com/health`; expect `ok`.
4. Note the service URL: this is `API_URL`.
5. Set `FRONTEND_URL` to your Cloudflare URL once step 4 is done (Environment > edit > Save; it redeploys). Do not add a trailing slash.

## 4. Cloudflare Pages (site)
1. In GitHub, edit `web/config.js`: set `api: "https://<service>.onrender.com"`. Commit to `main`.
2. dash.cloudflare.com > **Workers & Pages > Create > Pages > Connect to Git** > this repo.
3. Framework: None. Build command: empty. **Build output directory: `web`**. Save and Deploy.
4. Copy the `*.pages.dev` URL into Render's `FRONTEND_URL`. (Custom domain: Pages > Custom domains; then update `FRONTEND_URL` and `GMAIL_REDIRECT_URI` if relevant.)
5. `web/_headers` applies security headers automatically. If you use a custom API domain (not `onrender.com`), add it to `connect-src` there.

## 5. GitHub Actions secrets
Repo > Settings > Secrets and variables > Actions > **New repository secret**:

| Secret | Value | Needed by |
|---|---|---|
| `API_URL` | `https://<service>.onrender.com` (no trailing slash) | autopilot tick |
| `CRON_SECRET` | same as Render | autopilot tick |
| `DATABASE_URL` | same Neon URL | ingest |
| `RAPIDAPI_KEY` | rapidapi.com JSearch key (paid, adds contract roles) | ingest, optional |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | developer.adzuna.com (free) | ingest, optional |
| `USAJOBS_KEY`, `USAJOBS_EMAIL` | developer.usajobs.gov (free) | ingest, optional |

Then Actions tab > **Autopilot tick** > Run workflow, and **Job ingest** > Run workflow (mode: full). Both should go green. Ticks run hourly at :05; ingest alternates full/fast every hour.

## 6. Resend (email)
1. resend.com > **Domains > Add domain** (careerpilot.ai) > add the DNS records it shows at your DNS host > Verify.
2. **API Keys > Create** (sending access) > `RESEND_API_KEY`.
3. `MAIL_FROM` = `CareerPilot <noreply@careerpilot.ai>` (must be on the verified domain).

## 7. Stripe
1. dashboard.stripe.com > Developers > API keys: copy `STRIPE_SECRET_KEY` (sk_...) and `STRIPE_PUBLISHABLE_KEY` (pk_...). Start in test mode.
2. Create products/prices once (needs Python + `pip install stripe`, or a Colab cell): `STRIPE_SECRET_KEY=sk_... python server/setup_stripe.py`. Paste the printed `STRIPE_PRICE_*` values into Render.
3. Developers > Webhooks > **Add endpoint**: URL `https://<service>.onrender.com/api/billing/webhook`. Select events:
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_failed`
4. Copy the endpoint's **Signing secret** (whsec_...) into `STRIPE_WEBHOOK_SECRET`.
5. Settings > Billing > **Customer portal**: activate it (used by "Manage billing").
6. Going live: repeat with live keys, re-run setup_stripe.py, create a live webhook, update Render.

## 8. Gmail OAuth (send-from-Gmail)
1. console.cloud.google.com > new project > **APIs & Services > Library** > enable **Gmail API**.
2. **OAuth consent screen**: External, add app name, support email, your domain. Scopes: `openid`, `email`, `https://www.googleapis.com/auth/gmail.send`. While in "Testing", only listed test users can connect; `gmail.send` is a sensitive scope, so public launch needs Google verification (allow days to weeks).
3. **Credentials > Create OAuth client ID > Web application**. Authorized redirect URI: `https://<service>.onrender.com/api/integrations/gmail/callback`.
4. Copy Client ID / Secret to `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET`; set `GMAIL_REDIRECT_URI` to the same redirect URI exactly.

## 9. Twilio Verify (SMS verification)
1. twilio.com > Console: copy Account SID and Auth Token.
2. Verify > Services > **Create** > copy the Service SID (`VA...`).
3. Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_VERIFY_SERVICE_SID`. (Trial accounts only text verified numbers.)

## 10. Environment variables
| Name | Where from | Required |
|---|---|---|
| `ENV` | preset `prod` | yes |
| `DATABASE_URL` | Neon (step 2) | yes |
| `AUTH_SECRET` | step 1 | yes |
| `FRONTEND_URL` | Cloudflare URL | yes |
| `CRON_SECRET` | step 1 | yes (autopilot) |
| `AI_BASE_URL`, `AI_MODEL`, `AI_FAST_MODEL` | preset (Ashna gateway) | yes |
| `AI_API_KEY` | Ashna dashboard | yes (or `ANTHROPIC_API_KEY`) |
| `RESEND_API_KEY`, `MAIL_FROM` | step 6 | yes for support/digest email |
| `STRIPE_*` (8 values) | step 7 | for payments |
| `GMAIL_*`, `INTEGRATION_ENCRYPTION_KEY` | steps 8, 1 | for Gmail send |
| `TWILIO_*` (3 values) | step 9 | for SMS verify |
| `SENTRY_DSN`, UptimeRobot | optional; UptimeRobot: monitor `API_URL/health` every 5 min (also keeps Render awake) | no |

If Render logs say "refusing to start", the message lists exactly which required variable is wrong.

## 11. Post-deploy smoke test
- [ ] `API_URL/health` returns ok (first hit may take ~1 min: cold start)
- [ ] Site loads, jobs list shows real roles (after first ingest run)
- [ ] Browser console has no CSP errors on load, resume upload (PDF/DOCX) and checkout
- [ ] Sign up with email + password, sign out, sign in
- [ ] Autopilot tick workflow is green
- [ ] Ingest workflow is green
- [ ] Tailor a resume (AI works)
- [ ] Support ticket email arrives
- [ ] Stripe test checkout (card 4242 4242 4242 4242) upgrades the account; webhook shows 200 in Stripe

## 12. QA checklist
- [ ] Free plan shows 10 generations; Pro shows 400 after upgrade
- [ ] Billing portal opens; cancelling downgrades via webhook
- [ ] Failed payment (card 4000 0000 0000 0341) flags the account
- [ ] Gmail connect popup completes and a test send works
- [ ] SMS code arrives (Twilio)
- [ ] Recruiter account: bench limit enforced
- [ ] Autopilot: enable, wait for next :05 tick, digest email arrives
- [ ] Mobile layout on a phone; no horizontal scroll
- [ ] Wrong `X-Cron-Secret` on `/api/autopilot/tick` returns 401/403
