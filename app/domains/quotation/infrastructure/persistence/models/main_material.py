from typing import TYPE_CHECKING, Optional
from decimal import Decimal

from sqlalchemy import String, Integer, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base

if TYPE_CHECKING:
    from .estimation_work_item import EstimationWorkItemModel


class MainMaterialModel(Base):
    __tablename__ = "main_material"
    __table_args__ = {"schema": "quotation"}

    main_material_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    cost_item_id: Mapped[int] = mapped_column(
        ForeignKey("quotation.estimation_work_item.cost_item_id")
    )
    product_segment: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    product_line: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    product_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    layers: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    package_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    theoretical_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    construction_loss: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4), nullable=True)
    actual_rate_per_litter: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    actual_rate_per_box: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    box_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    color_mixing_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    unit_price_per_m2: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    percent_usage: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4), nullable=True)
    area: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    total_price_area_based: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    litters: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    boxes: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    total_price_round: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)

    cost_item: Mapped["EstimationWorkItemModel"] = relationship(
        back_populates="main_materials"
    )
