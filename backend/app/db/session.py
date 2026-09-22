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


def _ensure_conversation_document_column(bind_engine) -> None:
    """Backfill ``conversations.document_id`` on legacy databases.

    ``create_all`` never alters existing tables, so databases created
    before the document-scoped workspace feature get the new column here.
    Failing to backfill is non-fatal: chat still works, just without
    workspace-to-document binding for pre-existing rows.
    """

    def _migrate(connection) -> None:
        table_names = {
            name
            for name in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).scalars()
        }
        if "conversations" not in table_names:
            return
        columns = set()
        for _cid, name, *_rest in connection.exec_driver_sql(
            "PRAGMA table_info(conversations)"
        ).all():
            if name:
                columns.add(name)
        if "document_id" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE conversations ADD COLUMN document_id INTEGER "
                "REFERENCES documents(id) ON DELETE SET NULL"
            )

    try:
        with bind_engine.begin() as connection:
            _migrate(connection)
    except Exception:
        logger.warning(
            "Could not backfill conversations.document_id; continuing without it.",
            exc_info=True,
        )


def _ensure_summary_version_column(bind_engine) -> None:
    """Backfill ``summaries.version`` on legacy databases.

    ``create_all`` never alters existing tables, so databases created
    before the provider metadata change lack the ``version`` column. Old
    rows get a placeholder so reads stay safe; new summaries always store
    the current ``SUMMARY_CACHE_VERSION``.
    """

    def _migrate(connection) -> None:
        table_names = {
            name
            for name in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).scalars()
        }
        if "summaries" not in table_names:
            return
        columns = set()
        for _cid, name, *_rest in connection.exec_driver_sql(
            "PRAGMA table_info(summaries)"
        ).all():
            if name:
                columns.add(name)
        if "version" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE summaries ADD COLUMN version VARCHAR(64) DEFAULT 'legacy'"
            )

    try:
        with bind_engine.begin() as connection:
            _migrate(connection)
    except Exception:
        logger.warning(
            "Could not backfill summaries.version; continuing without it.",
            exc_info=True,
        )


def _ensure_report_metadata_columns(bind_engine) -> None:
    """Backfill ``documents.report_type`` / ``documents.report_header``.

    ``create_all`` never alters existing tables, so databases created
    before document-level chat kept the report identity columns here.
    Pre-existing rows keep ``NULL``; new uploads populate the columns.
    """

    def _migrate(connection) -> None:
        table_names = {
            name
            for name in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).scalars()
        }
        if "documents" not in table_names:
            return
        columns = set()
        for _cid, name, *_rest in connection.exec_driver_sql(
            "PRAGMA table_info(documents)"
        ).all():
            if name:
                columns.add(name)
        if "report_type" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE documents ADD COLUMN report_type VARCHAR(255)"
            )
        if "report_header" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE documents ADD COLUMN report_header VARCHAR(255)"
            )

    try:
        with bind_engine.begin() as connection:
            _migrate(connection)
    except Exception:
        logger.warning(
            "Could not backfill documents.report_type/report_header; "
            "continuing without them.",
            exc_info=True,
        )


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
    _ensure_conversation_document_column(engine)
    _ensure_summary_version_column(engine)
    _ensure_report_metadata_columns(engine)
    logger.info("Database tables initialised at %s", db_file)