# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Run the job ingest inside the API process.

GitHub Actions stays the scheduler, but a freshly deployed database has no jobs
until the first scheduled run lands, and a board with no roles looks broken.
So the API fills an empty board itself on startup, and the same code is
reachable through a cron-secret endpoint for an on-demand import.
"""
import logging
import threading
from types import SimpleNamespace

log = logging.getLogger("careerpilot.ingest")
_lock = threading.Lock()
_running = False


def running() -> bool:
    return _running


def _job(mode: str, max_seconds: int):
    global _running
    try:
        from api.db import SessionLocal
        from ingest import run as R
        a = SimpleNamespace(max_seconds=max_seconds, workers=4, agg_expire_days=21)
        db = SessionLocal()
        try:
            code = R.cycle(db, a, ats=(mode == "full"), agg=True)
            log.info("ingest (%s) finished with code %s", mode, code)
        finally:
            db.close()
    except Exception:
        log.exception("ingest (%s) crashed", mode)
    finally:
        with _lock:
            _running = False


def start(mode: str = "full", max_seconds: int = 600) -> bool:
    """Start one background ingest. False if one is already running."""
    global _running
    with _lock:
        if _running:
            return False
        _running = True
    threading.Thread(target=_job, args=(mode, max_seconds), daemon=True, name="ingest").start()
    return True


def ensure_board_not_empty() -> bool:
    """Called at startup: import once if there are no live jobs at all."""
    from api.db import SessionLocal
    from api.models import Job
    db = SessionLocal()
    try:
        empty = db.query(Job).filter(Job.active.is_(True)).first() is None
    finally:
        db.close()
    if empty:
        log.info("no live jobs found; starting the first import in the background")
        return start("full")
    return False
