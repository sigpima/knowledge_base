from typing import TYPE_CHECKING, List, Optional
from datetime import date

from sqlalchemy import String, Date
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base

if TYPE_CHECKING:
    from .quotation import QuotationModel


class ProjectModel(Base):
    __tablename__ = "project"
    __table_args__ = {"schema": "quotation"}

    project_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    # Duy nhất: DB là chốt chặn cuối cho hai lần ingest đồng thời cùng tên công trình.
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )
    address: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    source_file: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    # sha256 của nội dung file YAML đã chuẩn hoá (xem ingest/writer.py); cùng tên + cùng hash = nhập lại file cũ.
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    created_at: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
    )
    # Số ngày dự kiến hoàn thành cho từng giai đoạn, vd [30, 6] = giai
    # đoạn 1 mất 30 ngày, giai đoạn 2 mất 6 ngày.
    estimated_workdays: Mapped[Optional[List[int]]] = mapped_column(
        ARRAY(Integer),
        nullable=True,
    )

    quotations: Mapped[List["QuotationModel"]] = relationship(
        back_populates="project"
    )
