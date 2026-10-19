from decimal import Decimal

from sqlalchemy import String, Integer, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class QuotationPaymentTermModel(Base):
    __tablename__ = "payment_term"
    __table_args__ = {"schema": "quotation"}

    payment_term_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    quotation_id: Mapped[int] = mapped_column(
        ForeignKey("quotation.quotation.quotation_id", name="fk_quotation_payment_term")
    )
    sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    percentage: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
    )
    trigger_type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    trigger_description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
