"""SQLAlchemy engine, session factory, and table-initialisation helpers."""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import Base

logger = get_logger("db")

settings = get_settings()

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def enable_sqlite_foreign_keys(db_engine: Engine) -> None:
    """SQLite disables foreign-key enforcement by default. Turn it on.

    The pragma is per-connection, so a ``connect`` event listener is the
    safest place to enable it.
    """

    @event.listens_for(db_engine, "connect")
    def _set_fk(_dbapi_connection, _record):  # pragma: no cover – trivial
        cursor = _dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# Enable FK enforcement for the application engine
enable_sqlite_foreign_keys(engine)


def init_db() -> None:
    """Create every table (if it doesn't exist) and ensure data dirs exist.

    Importing ``app.db.models`` inside the body avoids circular imports
    while still registering every model on ``Base.metadata`` before
    ``create_all`` runs.
    """
    from app.db import models as _models  # noqa: F401 – register models

    db_file = Path(engine.url.database or "")
    if db_file.parent and db_file.parent != Path("."):
        db_file.parent.mkdir(parents=True, exist_ok=True)

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)

    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialised at %s", db_file)