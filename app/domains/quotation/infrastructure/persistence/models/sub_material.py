from typing import Optional
from decimal import Decimal

from sqlalchemy import String, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class SubMaterialModel(Base):
    __tablename__ = "sub_material"
    __table_args__ = {"schema": "quotation"}

    sub_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("quotation.project.project_id"))
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    total_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
