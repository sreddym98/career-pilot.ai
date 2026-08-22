"""Re-key jobs onto the ATS-id fingerprint.

`ingest/run.py` used to derive a job's primary key from its content --
company, title and location, normalised. That merges genuinely distinct
postings (the same title opened in three regions) and, because the key is a
primary key, could make a single flush insert duplicate rows. It now keys on
`source|source_id` wherever the connector supplies one, which is stable and
unique per ATS posting.

Changing the key function alone does not change any row already in the table.
Every existing job keeps its old content-derived fingerprint, the next ingest
inserts the same postings again under new keys, and the originals sit there
until the 10-day inactivity sweep removes them -- taking any application that
referenced them along too. This script closes that gap by rewriting the
existing keys, so the next ingest recognises what it already has.

Where an ingest has already run under the new scheme, both copies of the
posting are sitting in the table at once. Those are merged rather than
re-keyed: the newer row is kept, the older row's first_seen and seen_count are
folded into it, any application is moved across, and the stale row is dropped.

Idempotent: rows already on the new scheme are left alone, so running it twice
is a no-op. Run it once, before the next ingest, after pulling this change:

    python migrate_fingerprints.py            # report what would change
    python migrate_fingerprints.py --apply    # do it
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from api.db import engine, SessionLocal, IS_SQLITE, init_db
from api.models import Job, Application
from ingest.run import fingerprint

APPLY = "--apply" in sys.argv

# This may well run against a database the app has not started against yet, so
# bring the schema up first. Additive and idempotent — see db.add_missing_columns.
init_db()


def planned_changes(db):
    """Old key -> new key, for every job whose key would move."""
    moves = {}
    for j in db.query(Job).all():
        if not (j.source and j.source_id):
            continue                      # still content-keyed; nothing to do
        new = fingerprint(j.company, j.title, j.location, j.source, j.source_id)
        if new != j.fingerprint:
            moves[j.fingerprint] = new
    return moves


def main():
    db = SessionLocal()
    try:
        moves = planned_changes(db)
        total = db.query(Job).count()
        apps = db.query(Application).count()

        if not moves:
            print(f"Nothing to do — all {total} jobs are already on the ATS-id key.")
            return 0

        collisions = set(moves.values()) & (set(m for m in moves) - set(moves.values()))
        print(f"{len(moves)} of {total} jobs need re-keying ({apps} applications in table).")
        for old, new in list(moves.items())[:5]:
            print(f"  {old} -> {new}")
        if len(moves) > 5:
            print(f"  … and {len(moves) - 5} more")
        if collisions:
            print(f"  ! {len(collisions)} keys collide with an existing row; those are skipped")

        if not APPLY:
            print("\nDry run. Re-run with --apply to write these.")
            return 0

        # Never UPDATE a fingerprint in place: it is a primary key with a child
        # foreign key that is not ON UPDATE CASCADE, so renaming the parent
        # orphans the children mid-statement. Copy to the new key, move the
        # children onto it, then drop the old row — every step legal on its own,
        # on Postgres as well as SQLite, with no need to disable enforcement.
        rekeyed = merged = 0
        for old, new in moves.items():
            old_job = db.get(Job, old)
            if not old_job:
                continue
            twin = db.get(Job, new)

            if twin is None:
                clone = Job(**{c.name: getattr(old_job, c.name)
                               for c in Job.__table__.columns})
                clone.fingerprint = new
                db.add(clone)
                db.flush()
                rekeyed += 1
            else:
                # An ingest already inserted this posting under the new key, so
                # the old row is a stale twin. Fold its history into the keeper
                # rather than losing when it was first seen.
                twin.seen_count = (twin.seen_count or 1) + (old_job.seen_count or 1)
                if old_job.first_seen and (not twin.first_seen
                                           or old_job.first_seen < twin.first_seen):
                    twin.first_seen = old_job.first_seen
                merged += 1

            db.query(Application).filter(Application.fingerprint == old)\
              .update({"fingerprint": new}, synchronize_session=False)
            db.delete(old_job)
            db.commit()

        orphans = db.execute(text(
            "SELECT COUNT(*) FROM applications a WHERE a.fingerprint IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM jobs j WHERE j.fingerprint = a.fingerprint)"
        )).scalar()
        if IS_SQLITE:
            broken = db.execute(text("PRAGMA foreign_key_check")).fetchall()
            if broken:
                print(f"\n! {len(broken)} dangling references remain: {broken[:3]}")
                return 1

        print(f"\nRe-keyed {rekeyed}, merged {merged} duplicate rows away. "
              f"Jobs now: {db.query(Job).count()}. Orphaned applications: {orphans}.")
        return 1 if orphans else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
