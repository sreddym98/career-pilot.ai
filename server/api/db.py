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

def _ipv4_connect_args(u: str) -> dict:
    """Render's free instances have no IPv6 route. If the database host also
    resolves to IPv6, libpq may try that first and fail with "Network is
    unreachable". Pin an IPv4 address with `hostaddr` while keeping `host`,
    which libpq still uses for TLS verification and SNI (Neon routes on it).
    Resolved once per process, at connect time, so a changed address is
    picked up on the next restart. Any failure leaves libpq to resolve normally."""
    import os, socket
    from sqlalchemy.engine import make_url
    if os.environ.get("DB_FORCE_IPV4", "1") == "0":
        return {}
    host = None
    try:
        host = make_url(u).host
        if not host or host in ("localhost", "127.0.0.1"):
            return {}
        v4 = sorted({i[4][0] for i in socket.getaddrinfo(host, 5432, socket.AF_INET, socket.SOCK_STREAM)})
        print(f"[db] {host}: IPv4 {v4[:3]} -> pinning hostaddr", flush=True)
        return {"hostaddr": v4[0]} if v4 else {}
    except Exception as e:
        try:
            allv = sorted({i[4][0] for i in socket.getaddrinfo(host, 5432)})
        except Exception as e2:
            allv = [f"lookup failed: {e2}"]
        print(f"[db] no IPv4 for {host} ({type(e).__name__}: {e}); all addresses: {allv[:4]}", flush=True)
        return {}


url = settings.DATABASE_URL
IS_SQLITE = url.startswith("sqlite")

if IS_SQLITE and settings.ENV != "dev":
    # SQLite has no business holding production data, and reaching here means
    # DATABASE_URL was never set rather than that anyone chose it.
    raise RuntimeError(
        f"ENV={settings.ENV} but DATABASE_URL is SQLite ({url}). "
        "Set DATABASE_URL to your Postgres connection string."
    )

if IS_SQLITE:
    engine = create_engine(url, connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def _fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
else:
    # Small pool: one free Render instance talking to Neon, which also closes idle
    # connections when it scales to zero — hence pre_ping and a short recycle.
    engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5,
                           pool_recycle=300, connect_args=_ipv4_connect_args(url))

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
    if isinstance(d, bool):
        # Postgres rejects BOOLEAN DEFAULT 1; SQLite (older builds) rejects TRUE.
        if engine.dialect.name == "postgresql":
            return "TRUE" if d else "FALSE"
        return "1" if d else "0"
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
