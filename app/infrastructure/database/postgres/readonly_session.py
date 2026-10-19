from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.config.config import settings


def _require_readonly_url(url: str) -> str:
    if not url:
        raise RuntimeError(
            "DATABASE_URL_READONLY is not set — see "
            "README.md for setup"
        )
    return url


readonly_engine = create_engine(
    _require_readonly_url(settings.database_url_readonly),
    connect_args={"options": "-c default_transaction_read_only=on -c statement_timeout=5000"},
)
ReadonlySessionLocal = sessionmaker(bind=readonly_engine)
