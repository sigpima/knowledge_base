from typing import TYPE_CHECKING, Optional
from decimal import Decimal

from sqlalchemy import String, Integer, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base

if TYPE_CHECKING:
    from .labor_info import LaborInfoModel


class LaborInfoProcessModel(Base):
    __tablename__ = "labor_info_process"
    __table_args__ = {"schema": "quotation"}

    process_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    labor_id: Mapped[int] = mapped_column(
        ForeignKey("quotation.labor_info.labor_id")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    main_labors_kn: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    main_labors_out: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sub_labors_out: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    days: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    # Manday tự suy ra (= số thợ x số ngày), tài liệu nguồn không nêu trực tiếp.
    kn_manday: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    main_out_manday: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    sub_out_manday: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)

    labor_info: Mapped["LaborInfoModel"] = relationship(
        back_populates="processes"
    )
