from typing import TYPE_CHECKING, List, Optional
from decimal import Decimal

from sqlalchemy import Numeric, String, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .concept import association_table
from app.infrastructure.database import Base

if TYPE_CHECKING:
    from .package import QuotationPackageModel
    from .work_step import WorkStepModel
    from .concept import ConceptModel


class WorkItemModel(Base):
    __tablename__ = "work_item"
    __table_args__ = (
        Index("ix_work_item_unit_unit_price", "unit", "unit_price"),
        {"schema": "quotation"},
    )

    item_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )
    package_id: Mapped[int] = mapped_column(
        ForeignKey("quotation.package.package_id")
    )
    sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
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
    total_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
        nullable=True,
    )
    currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    # ORM object
    quotation_package: Mapped["QuotationPackageModel"] = relationship(
        back_populates="work_items"
    )
    work_steps: Mapped[List["WorkStepModel"]] = relationship(
        back_populates="work_item"
    )
    concepts: Mapped[List["ConceptModel"]] = relationship(
        secondary=association_table, back_populates="work_items"
    )
