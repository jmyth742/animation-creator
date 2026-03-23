"""Database engine, session factory, and FastAPI dependency."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker

from config import settings

# SQLite needs check_same_thread=False so background threads can share the engine.
connect_args = (
    {"check_same_thread": False}
    if settings.DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
)

# Thread-local scoped session — safe to use in background threads.
SessionLocal = scoped_session(
    sessionmaker(autocommit=False, autoflush=False, bind=engine)
)


class Base(DeclarativeBase):
    pass


# ── FastAPI dependency ────────────────────────────────────────────────────────

def get_db():
    """Yield a database session and ensure it is closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Startup helper ────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create all tables defined on Base.metadata (called at app startup)."""
    # Import models so their Table objects are registered on Base.metadata
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
