from typing import TYPE_CHECKING, Optional
from decimal import Decimal

from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base

if TYPE_CHECKING:
    from .work_item import WorkItemModel


class WorkStepModel(Base):
    __tablename__ = "work_step"
    __table_args__ = {"schema": "quotation"}

    step_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("quotation.work_item.item_id")
    )
    sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    layers: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    # This table has no separate "name" column -- the step's title/name is
    # stored in `description`.
    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    note: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    product_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    work_item: Mapped["WorkItemModel"] = relationship(
        back_populates="work_steps"
    )
