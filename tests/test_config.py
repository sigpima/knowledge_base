# tests/test_config.py
from app.infrastructure.config.config import Settings


def test_settings_default_database_url_has_no_personal_user(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.database_url == "postgresql+psycopg2://postgres:postgres@localhost:5432/knowledge_base"


def test_settings_reads_env_var_override(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://x@localhost:5432/other")
    settings = Settings(_env_file=None)
    assert settings.database_url == "postgresql+psycopg2://x@localhost:5432/other"


def test_settings_explicit_kwarg_overrides_default():
    settings = Settings(_env_file=None, mcp_server_port=9999)
    assert settings.mcp_server_port == 9999


def test_session_database_url_is_sourced_from_settings():
    from app.infrastructure.config.config import settings
    from app.infrastructure.database.postgres import session

    assert session.DATABASE_URL == settings.database_url
