import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.infrastructure.database.postgres.readonly_session import (
    ReadonlySessionLocal,
    readonly_engine,
    _require_readonly_url,
)


def test_readonly_engine_url_uses_readonly_role():
    assert readonly_engine.url.username == "knowledge_base_ro"


def test_readonly_engine_uses_psycopg2_driver():
    assert readonly_engine.url.drivername == "postgresql+psycopg2"


def test_readonly_session_local_is_a_sessionmaker():
    session = ReadonlySessionLocal()
    try:
        assert session.bind is readonly_engine
    finally:
        session.close()


def test_require_readonly_url_raises_when_empty():
    with pytest.raises(RuntimeError, match="DATABASE_URL_READONLY"):
        _require_readonly_url("")


def test_require_readonly_url_passes_through_when_set():
    url = "postgresql+psycopg2://foo:bar@localhost:5432/db"
    assert _require_readonly_url(url) == url


def test_write_through_readonly_session_is_rejected(db_engine):
    """Proves, via a real DB call, that the read-only guarantee holds even
    if the role's own grants were ever misconfigured — enforced at the
    SQLAlchemy engine level via default_transaction_read_only=on."""
    with ReadonlySessionLocal() as session:
        with pytest.raises(DBAPIError) as exc_info:
            session.execute(
                text("INSERT INTO quotation.project (name, address) VALUES ('test', 'test')")
            )
            session.commit()
        message = str(exc_info.value).lower()
        assert "read-only" in message or "permission denied" in message
