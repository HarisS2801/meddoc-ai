"""Shared test fixtures.

The ``db_engine`` fixture creates a disposable SQLite database per test
in a ``tmp_path`` directory.  ``db_session`` yields an ORM session bound
to that database.  ``client`` provides a ``TestClient`` wired to a
session-backed ``get_db`` override so no real data is touched.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.core.exceptions import register_exception_handlers
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.main import create_app


@pytest.fixture()
def db_engine(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    test_engine = create_engine(database_url, connect_args={"check_same_thread": False})
    enable_sqlite_foreign_keys(test_engine)
    Base.metadata.create_all(test_engine)
    yield test_engine
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    TestSession = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)  # noqa: N806
    session = TestSession()
    yield session
    session.close()


@pytest.fixture()
def client(db_engine):
    TestSession = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)  # noqa: N806

    def _override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()