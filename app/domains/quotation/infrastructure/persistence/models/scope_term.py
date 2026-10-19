from typing import Optional
from decimal import Decimal

from sqlalchemy import String, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class QuotationScopeTermModel(Base):
    __tablename__ = "scope_term"
    __table_args__ = {"schema": "quotation"}

    scope_term_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    quotation_id: Mapped[int] = mapped_column(
        ForeignKey("quotation.quotation.quotation_id", name="fk_quotation_scope_term")
    )
    scope_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    term_type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
        nullable=True,
    )
