from typing import TYPE_CHECKING, List, Optional
from decimal import Decimal

from sqlalchemy import Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base

if TYPE_CHECKING:
    from .total_detail import TotalDetailModel
    from .estimation_work_item import EstimationWorkItemModel


class EstimationModel(Base):
    __tablename__ = "estimation"
    __table_args__ = {"schema": "quotation"}

    estimation_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("quotation.project.project_id")
    )
    # Tổng chi phí dự toán (vật tư chính, vật tư phụ, nhân công, bảo hành,
    # chi phí khác) -- có thể tự suy luận bằng tổng các dòng TotalDetail
    # nếu tài liệu nguồn không nêu rõ.
    total_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
        nullable=True,
    )

    total_details: Mapped[List["TotalDetailModel"]] = relationship(
        back_populates="estimation"
    )
    estimation_work_items: Mapped[List["EstimationWorkItemModel"]] = relationship(
        back_populates="estimation"
    )
