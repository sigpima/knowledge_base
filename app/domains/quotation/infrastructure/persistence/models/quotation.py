from typing import TYPE_CHECKING, Dict, Any, List, Optional
from datetime import date
from decimal import Decimal

from sqlalchemy import String, Numeric, Date, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base

if TYPE_CHECKING:
    from .project import ProjectModel
    from .package import QuotationPackageModel
    from .scope_term import QuotationScopeTermModel
    from .payment_term import QuotationPaymentTermModel
    from .warranty_term import QuotationWarrantyTermModel


class QuotationModel(Base):
    __tablename__ = "quotation"
    __table_args__ = {"schema": "quotation"}

    quotation_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    quotation_code: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
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
    # Named `extra_metadata` in Python because `metadata` is reserved by
    # SQLAlchemy's declarative Base; the DB column itself stays "metadata".
    extra_metadata: Mapped[Dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        nullable=False,
    )

    project: Mapped["ProjectModel"] = relationship(
        back_populates="quotations"
    )
    packages: Mapped[List["QuotationPackageModel"]] = relationship(
        back_populates="quotation"
    )
    scope_terms: Mapped[List["QuotationScopeTermModel"]] = relationship()
    payment_terms: Mapped[List["QuotationPaymentTermModel"]] = relationship()
    warranty_term: Mapped[Optional["QuotationWarrantyTermModel"]] = relationship()
