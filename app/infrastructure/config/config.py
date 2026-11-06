from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/knowledge_base"
    database_url_readonly: str = ""
    api_host: str = "127.0.0.1"
    mcp_server_host: str = "127.0.0.1"
    mcp_server_port: int = 8002
    ingest_max_body_bytes: int = 1_000_000
    mcp_server_url: str = "http://127.0.0.1:8002/mcp"
    gemini_api_key: str = ""
    gemini_chat_model: str = "gemini-3.5-flash-lite"
    gemini_base_url: str = ""  # để trống = máy chủ Gemini mặc định
    gemini_embedding_model: str = "gemini-embedding-001"
    policy_min_score: float = 0.0  # ngưỡng điểm tối thiểu khi tìm tài liệu chính sách; 0 = không lọc
    chat_log_dir: str = "chat_logs"
    # API chat cho website (SSE): bật/tắt bản demo, giới hạn câu hỏi/phiên và địa chỉ lắng nghe.
    chat_demo_enabled: bool = True
    chat_max_question_chars: int = 500
    chat_max_turns_per_session: int = 30
    chat_session_ttl_seconds: int = 1800
    chat_max_sessions: int = 200
    chat_api_host: str = "127.0.0.1"
    chat_api_port: int = 8003
    log_level: str = "INFO"


settings = Settings()
