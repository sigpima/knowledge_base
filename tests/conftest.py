import os

import pytest

_TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
_TEST_DATABASE_URL_READONLY = os.getenv("TEST_DATABASE_URL_READONLY")

if not _TEST_DATABASE_URL or not _TEST_DATABASE_URL_READONLY:
    pytest.exit(
        "Đặt TEST_DATABASE_URL và TEST_DATABASE_URL_READONLY trỏ tới DB test, ví dụ: "
        "TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/knowledge_base_test "
        "TEST_DATABASE_URL_READONLY=postgresql+psycopg2://knowledge_base_ro:ro@localhost:5432/knowledge_base_test",
        returncode=2,
    )

# Phải đặt trước khi import app.*, vì Settings đọc biến môi trường lúc import.
os.environ["DATABASE_URL"] = _TEST_DATABASE_URL
os.environ["DATABASE_URL_READONLY"] = _TEST_DATABASE_URL_READONLY

from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.infrastructure.database import Base  # noqa: E402
from app.infrastructure.database.postgres.session import engine, SessionLocal  # noqa: E402
from app.domains.quotation.infrastructure.persistence import models as _quotation_models  # noqa: F401, E402


@pytest.fixture(scope="session")
def db_engine():
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS quotation"))
    Base.metadata.create_all(engine)
    read_only_user = make_url(_TEST_DATABASE_URL_READONLY).username
    with engine.begin() as conn:
        conn.execute(text(f'GRANT USAGE ON SCHEMA quotation TO "{read_only_user}"'))
        conn.execute(text(f'GRANT SELECT ON ALL TABLES IN SCHEMA quotation TO "{read_only_user}"'))
    yield engine
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS quotation CASCADE"))


def _truncate_all(session) -> None:
    tables = ", ".join(t.fullname for t in Base.metadata.sorted_tables)
    session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    session.commit()


@pytest.fixture
def db_session(db_engine):
    session = SessionLocal()
    _truncate_all(session)  # bắt đầu từ DB trống kể cả khi lần chạy trước để lại dữ liệu
    try:
        yield session
    finally:
        session.rollback()
        _truncate_all(session)
        session.close()
