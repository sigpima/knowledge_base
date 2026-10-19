from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/knowledge_base"
    database_url_readonly: str = ""
    mcp_server_host: str = "127.0.0.1"
    mcp_server_port: int = 8002
    ingest_max_body_bytes: int = 1_000_000
    log_level: str = "INFO"


settings = Settings()
