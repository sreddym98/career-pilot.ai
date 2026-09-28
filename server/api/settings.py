# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Relative to wherever the server is started, which is server/. An absolute
    # path to one developer's home directory is not a default anyone else — or
    # any container — can use, and silently running production on SQLite
    # because the variable was unset is worse than failing to start.
    DATABASE_URL: str = "sqlite:///./dev.db"
    REDIS_URL: str = "redis://localhost:6379/0"
    ANTHROPIC_API_KEY: str = ""
    # Sonnet writes the resumes and cover letters; Haiku does the high-volume
    # autopilot matching where cost per call matters more than prose quality.
    ANTHROPIC_MODEL: str = "claude-sonnet-5-5"
    ANTHROPIC_FAST_MODEL: str = "claude-haiku-4-5-20251001"
    # "auto" = Anthropic when a key is set, otherwise local Ollama (dev only).
    AI_PROVIDER: str = "auto"
    OLLAMA_URL: str = "http://localhost:11434"
    # Shared secret for the scheduled autopilot trigger (GitHub Actions cron).
    # Unset = the trigger endpoint stays closed.
    CRON_SECRET: str = ""
    # Outbound mail for support tickets and autopilot digests (Resend).
    RESEND_API_KEY: str = ""
    MAIL_FROM: str = "CareerPilot <noreply@careerpilot.ai>"
    SUPABASE_URL: str = ""
    SUPABASE_JWT_SECRET: str = ""
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_PRO_MONTHLY: str = ""
    STRIPE_PRICE_RECRUITER: str = ""
    STRIPE_PRICE_PRO_3MO: str = ""
    STRIPE_PRICE_PRO_6MO: str = ""
    STRIPE_PRICE_EVAL: str = ""
    RAPIDAPI_KEY: str = ""
    GMAIL_CLIENT_ID: str = ""
    GMAIL_CLIENT_SECRET: str = ""
    GMAIL_REDIRECT_URI: str = "http://localhost:8000/api/integrations/gmail/callback"
    INTEGRATION_ENCRYPTION_KEY: str = ""
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_VERIFY_SERVICE_SID: str = ""
    # Signs sessions we issue ourselves (email + password sign-in). Independent
    # of SUPABASE_JWT_SECRET so both can be live at once during a migration.
    AUTH_SECRET: str = ""
    AUTH_TOKEN_DAYS: int = 7
    FRONTEND_URL: str = "http://localhost:3000"
    ENV: str = "dev"
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()


def production_problems() -> list[str]:
    """Everything that must be true before this process may serve real users.

    Called at startup. ENV defaults to "dev", and dev means: anyone with no
    credential is silently signed in as a Pro account and CORS is wide open.
    That is right on a laptop and catastrophic on the internet, so a process
    that looks deployed (public FRONTEND_URL) but still says dev refuses to
    start rather than serving that.
    """
    problems = []
    looks_public = not settings.FRONTEND_URL.startswith(("http://localhost", "http://127.0.0.1"))
    if settings.ENV == "dev":
        if looks_public:
            problems.append("ENV=dev with a public FRONTEND_URL. Set ENV=prod — dev mode "
                            "signs every anonymous visitor in as a Pro user.")
        return problems
    if not settings.AUTH_SECRET:
        problems.append("AUTH_SECRET is not set")
    if settings.DATABASE_URL.startswith("sqlite"):
        problems.append("DATABASE_URL is SQLite; use Postgres")
    if not settings.ANTHROPIC_API_KEY and settings.AI_PROVIDER in ("auto", "anthropic"):
        problems.append("ANTHROPIC_API_KEY is not set (AI features would 503)")
    if settings.FRONTEND_URL.startswith("http://localhost"):
        problems.append("FRONTEND_URL still points at localhost (CORS, Stripe and OAuth redirects)")
    return problems


def auth_secret() -> str:
    """The key our own sessions are signed with.

    In dev we derive a stable throwaway key so `git clone && make dev` gets you
    a working login with nothing to configure — the same bargain SQLite and the
    AI demo mode already make. In prod an unset AUTH_SECRET is a hard failure,
    because the fallback would be a publicly known signing key.
    """
    if settings.AUTH_SECRET:
        return settings.AUTH_SECRET
    if settings.ENV == "dev":
        return "dev-only-insecure-signing-key-do-not-use-in-production"
    raise RuntimeError(
        "AUTH_SECRET is not set. Generate one with:\n"
        "  python -c \"import secrets; print(secrets.token_urlsafe(48))\""
    )


# ── Account types ────────────────────────────────────────────────────────────
# A seeker is looking for their own next role; a recruiter places other people.
# These are separate accounts, not a toggle: the two products share a job feed
# and almost nothing else, and letting one session hold both roles is how you
# end up leaking one recruiter's bench into another user's profile page.
ACCOUNT_TYPES = ("seeker", "recruiter")
DEFAULT_ACCOUNT_TYPE = "seeker"

# How many people a recruiter may keep on their bench. Signing up is free so
# the product can be evaluated with real candidates; the cap is what the paid
# plan lifts. None = no ceiling.
BENCH_LIMITS = {"free": 3, "pro": 3, "recruiter": 10, "enterprise": None}

# Generation allowances. Each AI call costs ~$0.02-0.05, so "unlimited"
# would lose money on power users. State the number instead of throttling quietly.
# Generations = tailored resume + cover letter, one pair per application.
# Free tier's 10 covers a light job search without ever paying; Pro's 400
# is a full-time search pace — roughly 13/day across a month.
PLAN_CREDITS = {"free": 10, "pro": 400, "recruiter": 400}
PLAN_PRICE_CENTS = {"pro": 11999, "pro_list": 14999, "recruiter": 16999}  # cents, USD
REFERRAL_BONUS = 100        # per active referral, per month
CREDIT_CAP = 700            # ceiling regardless of referral count — above Pro's 400 base + a few referrals
REFERRAL_QUALIFY_DAYS = 7   # referee must stay active this long to count
