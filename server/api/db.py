# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Database session management.

Uses Postgres in production. Falls back to SQLite automatically when no
DATABASE_URL is set, so you can run the whole API locally with zero setup
before you've touched Postgres at all.
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from api.settings import settings

url = settings.DATABASE_URL
IS_SQLITE = url.startswith("sqlite")

if IS_SQLITE:
    engine = create_engine(url, connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def _fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
else:
    engine = create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=20)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create every table. Idempotent — safe to run repeatedly."""
    from api.models import Base
    Base.metadata.create_all(engine)
    return sorted(Base.metadata.tables.keys())
