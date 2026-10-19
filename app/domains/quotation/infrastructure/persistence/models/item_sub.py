from typing import Optional
from decimal import Decimal

from sqlalchemy import Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class ItemSubModel(Base):
    __tablename__ = "item_sub"
    __table_args__ = {"schema": "quotation"}

    # Surrogate PK, not a composite (item_id, sub_id) PK -- item_id must be
    # allowed NULL when a vật tư phụ line can't be mapped to a hạng mục
    # (see note.md ItemSub Note), which a composite PK member can't be.
    item_sub_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("quotation.work_item.item_id"),
        nullable=True,
    )
    sub_id: Mapped[int] = mapped_column(
        ForeignKey("quotation.sub_material.sub_id")
    )
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    total_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
