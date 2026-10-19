from typing import TYPE_CHECKING, List

from sqlalchemy import String, ForeignKey, Table, Column, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base

if TYPE_CHECKING:
    from .work_item import WorkItemModel

association_table = Table(
    "work_item_concept",
    Base.metadata,
    Column("concept_id", ForeignKey("quotation.concept.concept_id"), primary_key=True),
    Column("item_id", ForeignKey("quotation.work_item.item_id"), primary_key=True),
    schema="quotation",
)

class ConceptModel(Base):
    __tablename__ = "concept"
    __table_args__ = (
        Index("ix_concept_type_name", "type", "name"),
        {"schema": "quotation"},
    )

    concept_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )
    work_items: Mapped[List["WorkItemModel"]] = relationship(
        secondary=association_table, back_populates="concepts"
    )
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
