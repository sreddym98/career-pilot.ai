# Security

## Secrets

Every secret lives in `server/.env`, which `.gitignore` excludes. Nothing
secret belongs in `web/index.html` — that file ships to every visitor.

A pre-commit hook blocks known key formats:

```bash
bash scripts/setup-hooks.sh          # install
bash scripts/check-secrets.sh --all  # scan every tracked file
```

## If a key is exposed

Rotate it. Deleting the commit is not sufficient — GitHub retains unreachable
objects, forks keep their own copies, and anything pushed publicly should be
assumed scraped within minutes.

| | |
|---|---|
| Stripe | Dashboard → Developers → API keys → **Roll key** |
| Anthropic | console.anthropic.com → API keys → revoke |
| Supabase | Settings → API → reset JWT secret |
| RapidAPI | App dashboard → regenerate |
| GitHub | Settings → Developer settings → revoke |

Rotating takes seconds and costs nothing. Hoping nobody noticed does not.

## Design decisions worth knowing

**The Anthropic key never reaches the browser.** All AI calls go through
`/api/ai/*`. The prototype called Anthropic directly from the client, which
would have exposed the key to every visitor — `server/api/routers/ai.py` is
the fix.

**Stripe webhooks are signature-verified.** Without
`stripe.Webhook.construct_event`, anyone who found the endpoint could POST
themselves a paid subscription. `test_billing.py` proves a forged webhook is
rejected and the account stays on the free plan.

**Card data never touches the server.** Stripe Checkout is a hosted redirect,
which keeps the application out of PCI-DSS scope entirely.

**Resumes are parsed in the browser.** PDF and Word files are read client-side
and never uploaded.

**Dev auth is dev-only.** With no `SUPABASE_JWT_SECRET` set, the API signs
everyone in as a shared local user so endpoints work without setup. Setting
`ENV=production` requires real JWT verification. Never deploy without it.

## Reporting

mamindlasreddy@gmail.com
