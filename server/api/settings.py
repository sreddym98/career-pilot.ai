# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
from pydantic import field_validator
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
    # Any OpenAI-compatible gateway (Ashna AI, OpenRouter, ...). Set AI_BASE_URL
    # to the URL that /chat/completions hangs off, e.g. https://api.ashna.ai/v1/api
    AI_BASE_URL: str = ""
    AI_API_KEY: str = ""
    AI_MODEL: str = "claude-sonnet-5"          # resumes, cover letters, evaluations
    AI_FAST_MODEL: str = "claude-haiku-4.5"    # high-volume autopilot tailoring
    # "auto" picks: gateway (AI_BASE_URL+AI_API_KEY) > Anthropic key > local Ollama (dev only).
    # Or force one of: openai | anthropic | ollama
    AI_PROVIDER: str = "auto"
    OLLAMA_URL: str = "http://localhost:11434"
    # Shared secret for the scheduled autopilot trigger (GitHub Actions cron).
    # Unset = the trigger endpoint stays closed.
    CRON_SECRET: str = ""
    # Fill an empty jobs table with a background import when the API boots.
    AUTO_INGEST_ON_EMPTY: bool = True
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
    # ── Hardening (rate limits, request caps, support mail) ──
    # All limits are per process (in-memory); fine for one Render instance.
    # *_WINDOW_S is the sliding window in seconds. RATE_LIMIT_ENABLED=false is
    # for local experiments only; tests run with it on.
    RATE_LIMIT_ENABLED: bool = True
    RATE_AUTH_PER_IP_EMAIL: int = 10     # sign-in/up attempts per IP+email
    RATE_AUTH_PER_IP: int = 30           # ... per IP
    RATE_AUTH_PER_EMAIL: int = 20        # ... per email from any IP (blocks IP rotation)
    RATE_AUTH_GLOBAL: int = 600          # ... whole server (ceiling if XFF is spoofed)
    RATE_AUTH_WINDOW_S: int = 900
    RATE_PHONE_START: int = 3            # Twilio SMS sends per user
    RATE_PHONE_START_PER_IP: int = 10    # ... per source IP (all accounts)
    RATE_PHONE_WINDOW_S: int = 3600
    RATE_GMAIL_START: int = 10
    RATE_GMAIL_WINDOW_S: int = 3600
    RATE_SUPPORT: int = 5                # tickets per user
    RATE_SUPPORT_WINDOW_S: int = 3600
    RATE_AI_PER_USER: int = 30           # /api/ai/* calls per user per window
    RATE_AI_PER_IP: int = 120
    RATE_AI_WINDOW_S: int = 60
    # Which X-Forwarded-For entry is the client when ENV != dev. 0 = first hop,
    # -1 = last (the address the platform proxy itself saw; unspoofable).
    TRUSTED_IP_HOP: int = 0
    MAX_BODY_BYTES: int = 1_000_000
    MAX_WEBHOOK_BODY_BYTES: int = 5_000_000
    # Comma-separated. Only these accounts may read/resolve the support queue.
    ADMIN_EMAILS: str = ""
    SUPPORT_EMAIL: str = ""              # empty = don't email new tickets
    @field_validator("FRONTEND_URL")
    @classmethod
    def _no_trailing_slash(cls, v: str) -> str:
        """CORS compares origins exactly, and every redirect appends "/..." to
        this value, so a stray trailing slash silently breaks the browser (CORS
        errors, "//?upgraded=1"). Normalise once here."""
        return v.strip().rstrip("/")

    @field_validator("DATABASE_URL")
    @classmethod
    def _driver(cls, v: str) -> str:
        """Neon, Render and Heroku hand out postgres:// or postgresql:// URLs,
        which SQLAlchemy resolves to psycopg2. This project ships psycopg 3
        only, so name the driver here and every consumer (API, ingest, seed)
        gets a URL that works."""
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

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
    if not (settings.AI_API_KEY and settings.AI_BASE_URL) and not settings.ANTHROPIC_API_KEY \
            and settings.AI_PROVIDER != "ollama":
        problems.append("No AI provider configured: set AI_BASE_URL + AI_API_KEY "
                        "(or ANTHROPIC_API_KEY) — AI features would 503")
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

