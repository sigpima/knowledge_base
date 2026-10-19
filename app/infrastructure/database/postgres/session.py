from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.infrastructure.config.config import settings
from app.infrastructure.database import Base
from app.domains.quotation.infrastructure.persistence import models as _quotation_models  # noqa: F401  (registers ORM models on Base.metadata)

DATABASE_URL = settings.database_url

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS quotation"))
    Base.metadata.create_all(engine)
