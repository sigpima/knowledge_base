from typing import Dict, Any, Optional
from datetime import date
from decimal import Decimal

from sqlalchemy import String, Numeric, Date, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class ExtraQuotationModel(Base):
    __tablename__ = "extra_quotation"
    __table_args__ = {"schema": "quotation"}

    extra_quotation_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("quotation.project.project_id")
    )
    issue_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
    )
    total_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
        nullable=True,
    )
    currency: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
    )
    description: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    quantity: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
        nullable=True,
    )
    unit: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )
    unit_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
        nullable=True,
    )
    extra_metadata: Mapped[Dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        nullable=False,
    )
