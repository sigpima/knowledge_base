from typing import TYPE_CHECKING, List, Optional
from decimal import Decimal

from sqlalchemy import String, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base

if TYPE_CHECKING:
    from .estimation import EstimationModel
    from .work_item import WorkItemModel
    from .labor_info import LaborInfoModel
    from .main_material import MainMaterialModel


class EstimationWorkItemModel(Base):
    __tablename__ = "estimation_work_item"
    __table_args__ = {"schema": "quotation"}

    cost_item_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    estimation_id: Mapped[int] = mapped_column(
        ForeignKey("quotation.estimation.estimation_id")
    )
    # Liên kết lỏng (nullable) tới hạng mục phía báo giá -- không phải mọi
    # hạng mục dự toán đều map được 1-1 sang WorkItem, theo thiết kế.
    item_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("quotation.work_item.item_id"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    main_unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    sub_unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    material_unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    total_price_area_based: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    total_price_round: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    material_unit_price_with_color_mixing_cost: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2), nullable=True
    )
    labor_unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    profit_margin: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4), nullable=True)

    estimation: Mapped["EstimationModel"] = relationship(
        back_populates="estimation_work_items"
    )
    work_item: Mapped[Optional["WorkItemModel"]] = relationship()
    labor_info: Mapped[Optional["LaborInfoModel"]] = relationship(
        back_populates="cost_item"
    )
    main_materials: Mapped[List["MainMaterialModel"]] = relationship(
        back_populates="cost_item"
    )
