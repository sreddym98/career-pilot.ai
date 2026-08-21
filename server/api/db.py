# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Database session management.

Uses Postgres in production. Falls back to SQLite automatically when no
DATABASE_URL is set, so you can run the whole API locally with zero setup
before you've touched Postgres at all.
"""
from sqlalchemy import create_engine, event, inspect, text
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
    add_missing_columns(Base)
    return sorted(Base.metadata.tables.keys())


def _default_sql(col):
    """Render a column's Python-side default as a SQL literal, or None if it
    can't be expressed as one."""
    if col.server_default is not None:
        return None                      # already carried in the type DDL
    d = getattr(col.default, "arg", None) if col.default is not None else None
    if callable(d) or d is None:
        return None
    if isinstance(d, bool):  return "1" if d else "0"
    if isinstance(d, (int, float)): return str(d)
    if isinstance(d, str):   return "'" + d.replace("'", "''") + "'"
    return None


def add_missing_columns(Base):
    """Add columns the models declare but the live tables lack.

    create_all() only ever CREATEs — it will not touch a table that already
    exists, so adding a field to a model leaves every existing database
    silently missing it. This project has no alembic history, and blowing away
    dev.db on every schema change is not an acceptable answer once there is
    real data in it.

    Deliberately only ADDs. Dropping or retyping a column can destroy data, so
    anything beyond an additive change is left to a human and a real migration.
    """
    insp = inspect(engine)
    added = []
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            live = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in live:
                    continue
                ddl = f"{col.name} {col.type.compile(engine.dialect)}"
                default = _default_sql(col)
                if not col.nullable:
                    if default is None:
                        # NOT NULL with no expressible default can't be added to
                        # a table that already has rows. Say so instead of
                        # raising an opaque database error at first request.
                        print(f"  ! {table.name}.{col.name} needs a manual migration "
                              f"(NOT NULL with no literal default)")
                        continue
                    ddl += f" NOT NULL DEFAULT {default}"
                elif default is not None:
                    ddl += f" DEFAULT {default}"
                conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {ddl}"))
                added.append(f"{table.name}.{col.name}")
    if added:
        print(f"  + added columns: {', '.join(added)}")
    return added
