# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Tiered polling. Fresh where it matters, sustainable everywhere else.

WHY NOT EVERYTHING EVERY 5 MINUTES
----------------------------------
  400 ATS boards ÷ 5 min  = 115,200 requests/day
  Greenhouse and Lever will rate-limit you within hours and block the IP
  within days. You also gain nothing: a company posts a job maybe twice a
  week, so 287 of every 288 polls return byte-identical data.

  Metered APIs are worse. JSearch at 5-minute polling across 6 queries is
  ~10,000 calls/day against a plan that gives you 10,000 a MONTH.

WHAT ACTUALLY WORKS
-------------------
  Match the poll rate to how fast each source really changes:

    FAST   every 10 min   aggregators, date_posted=today only
                          this is where new contract roles appear first
    WARM   every 2 hours  ATS boards that posted something in the last week
    SLOW   every 12 hours everything else
    SWEEP  nightly        full pass, expire anything that vanished

  A board that goes quiet drifts from FAST to SLOW automatically. A board
  that starts posting gets promoted. You end up polling the ~15% of sources
  that are actually active, which is where near-real-time freshness comes
  from — not from hammering all of them.

RESULT
------
  New jobs surface within 10-20 minutes instead of once a day, at roughly
  4,000 requests/day instead of 115,000.
"""
import datetime as dt

FAST, WARM, SLOW = "fast", "warm", "slow"

INTERVAL = {FAST: 10 * 60, WARM: 2 * 3600, SLOW: 12 * 3600}

# Promote/demote thresholds, in days since that source last produced a new job
PROMOTE_WARM_DAYS = 7
PROMOTE_FAST_DAYS = 1


def tier_for(last_new_at, is_aggregator=False, now=None):
    """Aggregators stay FAST — they're the freshness engine and they're
    cheap per call when scoped to date_posted=today."""
    if is_aggregator:
        return FAST
    if not last_new_at:
        return SLOW
    now = now or dt.datetime.now(dt.timezone.utc)
    if last_new_at.tzinfo is None:
        last_new_at = last_new_at.replace(tzinfo=dt.timezone.utc)
    days = (now - last_new_at).days
    if days <= PROMOTE_FAST_DAYS:
        return WARM          # even a hot ATS board rarely justifies 10-min polls
    if days <= PROMOTE_WARM_DAYS:
        return WARM
    return SLOW


def due(last_polled_at, tier, now=None):
    if not last_polled_at:
        return True
    now = now or dt.datetime.now(dt.timezone.utc)
    if last_polled_at.tzinfo is None:
        last_polled_at = last_polled_at.replace(tzinfo=dt.timezone.utc)
    return (now - last_polled_at).total_seconds() >= INTERVAL[tier]


def daily_request_estimate(counts):
    """counts = {'fast': n, 'warm': n, 'slow': n} → requests/day"""
    per_day = {FAST: 86400 / INTERVAL[FAST],
               WARM: 86400 / INTERVAL[WARM],
               SLOW: 86400 / INTERVAL[SLOW]}
    return sum(counts.get(t, 0) * per_day[t] for t in per_day)


def explain(counts):
    total = daily_request_estimate(counts)
    naive = sum(counts.values()) * (86400 / 300)
    return (f"{int(total):,} requests/day across {sum(counts.values())} sources "
            f"(polling everything every 5 min would be {int(naive):,} — "
            f"{naive/max(total,1):.0f}x more, for almost no extra freshness)")


if __name__ == "__main__":
    print(__doc__)
    for label, c in [("starter (100 boards)", {FAST: 8, WARM: 20, SLOW: 72}),
                     ("scaled  (400 boards)", {FAST: 8, WARM: 70, SLOW: 322}),
                     ("large   (1000 boards)", {FAST: 10, WARM: 150, SLOW: 840})]:
        print(f"  {label}:  {explain(c)}")
