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


def test_chat_defaults(monkeypatch):
    for name in (
        "CHAT_DEMO_ENABLED",
        "CHAT_MAX_QUESTION_CHARS",
        "CHAT_MAX_TURNS_PER_SESSION",
        "CHAT_SESSION_TTL_SECONDS",
        "CHAT_MAX_SESSIONS",
        "CHAT_API_HOST",
        "CHAT_API_PORT",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert settings.chat_demo_enabled is True
    assert settings.chat_max_question_chars == 500
    assert settings.chat_max_turns_per_session == 30
    assert settings.chat_session_ttl_seconds == 1800
    assert settings.chat_max_sessions == 200
    assert settings.chat_api_host == "127.0.0.1"
    assert settings.chat_api_port == 8003


def test_chat_demo_can_be_disabled_by_env(monkeypatch):
    monkeypatch.setenv("CHAT_DEMO_ENABLED", "false")
    assert Settings(_env_file=None).chat_demo_enabled is False


def test_policy_rag_defaults(monkeypatch):
    for name in ("GEMINI_EMBEDDING_MODEL", "POLICY_MIN_SCORE"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert settings.gemini_embedding_model == "gemini-embedding-001"
    assert settings.policy_min_score == 0.0


def test_milvus_defaults(monkeypatch):
    for name in ("MILVUS_URI", "MILVUS_TOKEN", "MILVUS_COLLECTION"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert settings.milvus_uri == "http://127.0.0.1:19530"
    assert settings.milvus_token == ""
    assert settings.milvus_collection == "policy_chunks"


def test_policy_min_score_accepts_values_in_cosine_range(monkeypatch):
    for value, expected in (("0", 0.0), ("-1", -1.0), ("1", 1.0), ("0.35", 0.35)):
        monkeypatch.setenv("POLICY_MIN_SCORE", value)
        assert Settings(_env_file=None).policy_min_score == expected


def test_policy_min_score_outside_cosine_range_is_rejected(monkeypatch):
    import pytest
    from pydantic import ValidationError

    for value in ("8", "1.01", "-1.5"):
        monkeypatch.setenv("POLICY_MIN_SCORE", value)
        with pytest.raises(ValidationError):
            Settings(_env_file=None)
