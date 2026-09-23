#!/usr/bin/env python3
"""
Test the autopilot engine end-to-end.

Usage:
    source .venv/bin/activate
    python test_autopilot.py
"""

import os
import sys
import asyncio
sys.path.insert(0, 'server')

from api.db import SessionLocal, init_db
from api.models import User, Job
from api.autopilot import AutopilotEngine


async def test_autopilot():
    """Test the full autopilot pipeline."""

    db = SessionLocal()

    # Create tables if needed
    init_db()

    # Get or create test user
    user = db.query(User).filter(User.email == "test@example.com").first()
    if not user:
        user = User(
            email="test@example.com",
            full_name="Test User",
            phone="+1 555-1234",
            skills=["Python", "FastAPI", "SQL"],
            role_families=["be", "de"]
        )
        db.add(user)
        db.commit()
        print(f"✓ Created test user: {user.email}")

    # Get some real jobs from the database
    jobs = db.query(Job).filter(Job.active == True).limit(3).all()

    if not jobs:
        print("❌ No jobs in database. Run: python server/ingest/run.py --once")
        return

    print(f"\n✓ Found {len(jobs)} jobs to test")
    for job in jobs:
        print(f"  - {job.title} at {job.company}")

    # Check API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("\n⚠️  ANTHROPIC_API_KEY not set. Set it with:")
        print('   export ANTHROPIC_API_KEY="your_key_here"')
        print("\nUsing mock mode for this test...\n")
        mock_mode = True
    else:
        mock_mode = False

    # Run autopilot
    print("\n🚀 Running autopilot...\n")
    engine = AutopilotEngine(db, user)

    try:
        results = await engine.apply_to_jobs(jobs, auto_approve=True, max_per_run=3)

        print("\n" + "=" * 80)
        print("AUTOPILOT RESULTS")
        print("=" * 80)
        print(f"Total applications: {results['total']}")
        print(f"Submitted: {results['submitted']}")
        print(f"Failed: {results['failed']}")
        print(f"Needs review: {results['needs_review']}")
        print(f"Success rate: {results['success_rate']:.0f}%")

        print("\nDetails:")
        for result in results['results']:
            status = "✅" if result.get('success') else "❌"
            print(f"{status} {result['job_title']} at {result['company']}")
            if result.get('error'):
                print(f"   Error: {result['error']}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    db.close()


if __name__ == "__main__":
    asyncio.run(test_autopilot())
