# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg://postgres:dev@localhost:5432/careerpilot"
    REDIS_URL: str = "redis://localhost:6379/0"
    ANTHROPIC_API_KEY: str = ""
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
    FRONTEND_URL: str = "http://localhost:3000"
    ENV: str = "dev"
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

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
