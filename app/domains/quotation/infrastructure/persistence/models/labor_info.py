from typing import TYPE_CHECKING, List, Optional
from decimal import Decimal

from sqlalchemy import String, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base

if TYPE_CHECKING:
    from .estimation_work_item import EstimationWorkItemModel
    from .labor_info_process import LaborInfoProcessModel


class LaborInfoModel(Base):
    __tablename__ = "labor_info"
    __table_args__ = {"schema": "quotation"}

    labor_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    cost_item_id: Mapped[int] = mapped_column(
        ForeignKey("quotation.estimation_work_item.cost_item_id"),
        unique=True,
    )
    area: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    kn_manday: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    main_out_manday: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    sub_out_manday: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    kn_total_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    main_out_total_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    sub_out_total_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    kn_out_total_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    # "all_out" (thuê ngoài toàn bộ) hoặc "has_kn" (có thợ kiêm nhiệm nội bộ).
    final_unit_price_type: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    labor_coeff: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4), nullable=True)
    labor_unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)

    cost_item: Mapped["EstimationWorkItemModel"] = relationship(
        back_populates="labor_info"
    )
    processes: Mapped[List["LaborInfoProcessModel"]] = relationship(
        back_populates="labor_info"
    )
