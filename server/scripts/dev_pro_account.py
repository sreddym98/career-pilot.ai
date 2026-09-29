# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Create (or reset) a LOCAL Pro test account with a complete profile and
Autopilot switched on, for hands-on QA.

    cd server
    ENV=dev DATABASE_URL=sqlite:///./qa_ap2.db python scripts/dev_pro_account.py
    ENV=dev DATABASE_URL=sqlite:///./qa_ap2.db python scripts/dev_pro_account.py \
        --email me@qa-local.dev --password 'Passw0rd!x' --skills "Cypress,Selenium,Java"

DEV ONLY. It writes a Pro plan straight into the database, which is exactly
what must never happen on a real one, so it refuses unless ENV=dev and the
database is not a hosted Postgres. There is no override flag.

The account gets: plan=pro, a saved profile (skills, one position, H1B work
authorization), resume confirmed, Autopilot ON with slots at 9/13/17 in the
given time zone. Re-running resets the same email in place.
"""
import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from api.settings import settings  # noqa: E402

if settings.ENV != "dev":
    sys.exit(f"REFUSING: ENV={settings.ENV!r}. This script grants a Pro plan directly in the "
             "database and only runs with ENV=dev.")
if not settings.DATABASE_URL.startswith("sqlite") and "localhost" not in settings.DATABASE_URL \
        and "127.0.0.1" not in settings.DATABASE_URL:
    sys.exit("REFUSING: DATABASE_URL does not look like a local database.")

from api.db import SessionLocal, init_db  # noqa: E402
from api.models import AutopilotConfig, Position, User, UserSkill  # noqa: E402
from api.passwords import hash_password  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", default="pro@qa-local.dev")
    ap.add_argument("--password", default="LocalPro!2026")
    ap.add_argument("--name", default="Local Pro Tester")
    ap.add_argument("--skills", default="Cypress,Selenium,Java,Playwright,API Testing,Postman,CI/CD,SQL")
    ap.add_argument("--tz", default="America/Chicago")
    ap.add_argument("--no-autopilot", action="store_true", help="leave Autopilot off (still confirmed)")
    a = ap.parse_args()

    init_db()
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == a.email.lower()).first()
        if not u:
            u = User(email=a.email.lower(), referral_code="dev" + os.urandom(4).hex())
            db.add(u)
        u.name, u.account_type, u.plan = a.name, "seeker", "pro"
        u.password_hash = hash_password(a.password)
        u.headline, u.location = "Senior SDET", "St. Louis, MO"
        u.summary = "Test automation engineer focused on web and API quality."
        u.work_auth = ["h1b"]
        u.credits_used = 0
        db.commit(); db.refresh(u)

        db.query(UserSkill).filter(UserSkill.user_id == u.id).delete()
        for i, sk in enumerate(s.strip() for s in a.skills.split(",") if s.strip()):
            db.add(UserSkill(user_id=u.id, skill=sk, is_top=i < 3))
        db.query(Position).filter(Position.user_id == u.id).delete()
        db.add(Position(user_id=u.id, company="Acme Payments", role="Senior SDET",
                        started_on=dt.date(2019, 6, 1), location="St. Louis, MO",
                        bullets=["Built Cypress and Selenium suites covering payment flows",
                                 "Automated REST API checks with Postman and wired them into CI/CD"]))
        cfg = db.get(AutopilotConfig, u.id)
        if not cfg:
            cfg = AutopilotConfig(user_id=u.id)
            db.add(cfg)
        cfg.resume_confirmed, cfg.on = True, not a.no_autopilot
        cfg.slots, cfg.tz, cfg.titles, cfg.skills, cfg.work_style = [9, 13, 17], a.tz, [], [], ""
        cfg.min_fit, cfg.paused_until, cfg.last_run_key, cfg.email_digest = 60, None, None, True
        db.commit()
        print(f"Local Pro account ready: {a.email} / {a.password}  (plan=pro, Autopilot "
              f"{'ON' if cfg.on else 'off'}, {a.tz})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
