"""Database engine, session factory, and FastAPI dependency."""

from sqlalchemy import create_engine, text
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

def _migrate_db() -> None:
    """Add columns introduced after the initial schema. Safe to run repeatedly."""
    migrations = [
        "ALTER TABLE scenes ADD COLUMN reference_image_path VARCHAR(1024)",
        """CREATE TABLE IF NOT EXISTS scene_clip_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_id INTEGER NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
            clip_path VARCHAR(1024) NOT NULL,
            quality VARCHAR(32),
            visual_style TEXT,
            tone TEXT,
            prompt TEXT,
            seed_image VARCHAR(1024),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""",
        "ALTER TABLE generation_jobs ADD COLUMN cancelled_at DATETIME",
        # ── Training support ──────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS training_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            character_id INTEGER REFERENCES characters(id) ON DELETE SET NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            progress_pct INTEGER NOT NULL DEFAULT 0,
            log_text TEXT NOT NULL DEFAULT '',
            gpu_type VARCHAR(255) DEFAULT 'NVIDIA RTX A6000',
            dataset_path VARCHAR(1024),
            character_name VARCHAR(255),
            trigger_word VARCHAR(255),
            rank INTEGER DEFAULT 32,
            epochs INTEGER DEFAULT 150,
            learning_rate VARCHAR(32) DEFAULT '1e-4',
            lora_path VARCHAR(1024),
            lora_strength REAL DEFAULT 0.7,
            pod_id VARCHAR(255),
            pod_ssh_host VARCHAR(255),
            pod_ssh_port INTEGER,
            training_loss REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            cancelled_at DATETIME
        )""",
        "ALTER TABLE characters ADD COLUMN lora_path VARCHAR(1024)",
        "ALTER TABLE characters ADD COLUMN lora_strength REAL DEFAULT 0.7",
        "ALTER TABLE training_jobs ADD COLUMN parent_id INTEGER REFERENCES training_jobs(id) ON DELETE SET NULL",
        "ALTER TABLE training_jobs ADD COLUMN attempt INTEGER DEFAULT 1",
        "ALTER TABLE characters ADD COLUMN trigger_word VARCHAR(255)",
        # ── Location LoRA support ────────────────────────────────────────
        "ALTER TABLE locations ADD COLUMN lora_path VARCHAR(1024)",
        "ALTER TABLE locations ADD COLUMN lora_strength REAL DEFAULT 0.5",
        "ALTER TABLE locations ADD COLUMN trigger_word VARCHAR(255)",
        "ALTER TABLE training_jobs ADD COLUMN location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL",
    ]
    with engine.connect() as conn:
        for stmt in migrations:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # Column already exists — ignore


def init_db() -> None:
    """Create all tables defined on Base.metadata (called at app startup)."""
    # Import models so their Table objects are registered on Base.metadata
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_db()
