from typing import Optional
from decimal import Decimal

from sqlalchemy import String, Integer, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class ProductToBuyModel(Base):
    __tablename__ = "product_to_buy"
    __table_args__ = {"schema": "quotation"}

    buy_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("quotation.project.project_id"))
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    package_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    boxes: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    boxes_round: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    boxes_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    boxes_unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    mini_package_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    mini_boxes_round: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mini_boxes_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    mini_boxes_unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    total_price_round: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
