from typing import TYPE_CHECKING, List, Optional
from decimal import Decimal

from sqlalchemy import String, Integer, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base

if TYPE_CHECKING:
    from .quotation import QuotationModel
    from .work_item import WorkItemModel


class QuotationPackageModel(Base):
    __tablename__ = "package"
    __table_args__ = {"schema": "quotation"}

    package_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    quotation_id: Mapped[int] = mapped_column(
        ForeignKey("quotation.quotation.quotation_id", name="fk_quotation_package")
    )
    sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    total_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
        nullable=True,
    )

    quotation: Mapped["QuotationModel"] = relationship(
        back_populates="packages"
    )
    work_items: Mapped[List["WorkItemModel"]] = relationship(
        back_populates="quotation_package"
    )
