from typing import TYPE_CHECKING
from decimal import Decimal

from sqlalchemy import String, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base

if TYPE_CHECKING:
    from .estimation import EstimationModel


class TotalDetailModel(Base):
    __tablename__ = "total_detail"
    __table_args__ = {"schema": "quotation"}

    total_detail_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    estimation_id: Mapped[int] = mapped_column(
        ForeignKey("quotation.estimation.estimation_id")
    )
    # Loại chi phí/lợi nhuận: vật tư chính, vật tư phụ, nhân công, chi phí
    # khác, bảo hành, lợi nhuận thuần, incentive, lợi nhuận cuối.
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    price: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
    )

    estimation: Mapped["EstimationModel"] = relationship(
        back_populates="total_details"
    )
