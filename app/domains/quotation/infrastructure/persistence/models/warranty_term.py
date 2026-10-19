from decimal import Decimal

from sqlalchemy import String, Integer, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class QuotationWarrantyTermModel(Base):
    __tablename__ = "warranty_term"
    __table_args__ = {"schema": "quotation"}

    warranty_term_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    quotation_id: Mapped[int] = mapped_column(
        ForeignKey("quotation.quotation.quotation_id", name="fk_quotation_warranty_term"),
        unique=True,
    )
    period: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    period_unit: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    extend_percent: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
    )
    extend_period: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
