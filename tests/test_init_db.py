import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.infrastructure.database.postgres.session import engine
from scripts.init_db import ensure_readonly_role, main

ROLE = "kb_ro_check"


@pytest.fixture
def cleanup_role(db_engine):
    yield
    with engine.begin() as conn:
        if conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROLE}).first():
            conn.execute(text(f"DROP OWNED BY {ROLE}"))
            conn.execute(text(f"DROP ROLE {ROLE}"))


def _engine_as(password: str):
    return create_engine(engine.url.set(username=ROLE, password=password))


def test_ensure_readonly_role_allows_select_and_blocks_writes(db_engine, cleanup_role):
    ensure_readonly_role(engine, ROLE, "pw-one")

    as_role = _engine_as("pw-one")
    with as_role.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM quotation.project")).scalar_one() == 0
    with pytest.raises(DBAPIError):
        with as_role.begin() as conn:
            conn.execute(text("INSERT INTO quotation.project (name, address) VALUES ('x', 'y')"))
    as_role.dispose()


def test_ensure_readonly_role_is_idempotent_and_updates_password(db_engine, cleanup_role):
    ensure_readonly_role(engine, ROLE, "pw-one")
    ensure_readonly_role(engine, ROLE, "pw-two")

    as_role = _engine_as("pw-two")
    with as_role.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar_one() == 1
    as_role.dispose()


def test_ensure_readonly_role_quotes_hostile_password(db_engine, cleanup_role):
    password = "it's \"quoted\"; DROP TABLE quotation.project; --"
    ensure_readonly_role(engine, ROLE, password)

    as_role = _engine_as(password)
    with as_role.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar_one() == 1
    as_role.dispose()


def test_main_requires_ro_password(monkeypatch):
    monkeypatch.delenv("RO_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="RO_PASSWORD"):
        main()
