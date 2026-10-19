"""Ghi một file báo giá đã kiểm tra vào DB trong đúng một transaction."""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.quotation.infrastructure.persistence.models import (
    ProjectModel,
    QuotationModel,
    QuotationPackageModel,
    QuotationPaymentTermModel,
    QuotationScopeTermModel,
    QuotationWarrantyTermModel,
    WorkItemModel,
)
from app.domains.quotation.infrastructure.persistence.repositories.estimation_repository import (
    SqlAlchemyEstimationRepository,
)
from app.domains.quotation.infrastructure.persistence.repositories.extra_quotation_repository import (
    SqlAlchemyExtraQuotationRepository,
)
from app.domains.quotation.infrastructure.persistence.repositories.quotation_repository import (
    SqlAlchemyQuotationRepository,
)
from app.infrastructure.observability.logger import get_logger

from .mapper import TermsData, to_estimation_bundle, to_extra_quotations, to_knowledge, to_terms
from .schema import QuotationFile

logger = get_logger(__name__)


class DuplicateProjectError(Exception):
    """Đã có công trình cùng tên trong DB."""


@dataclass
class IngestResult:
    project_id: int
    quotation_id: int
    work_item_count: int
    has_estimation: bool
    extra_count: int


def write_terms(session: Session, quotation_id: int, terms: TermsData) -> None:
    """Ghi điều khoản phạm vi/thanh toán/bảo hành (chưa có repository nào ghi các bảng này)."""
    for term in terms.scope:
        session.add(QuotationScopeTermModel(
            quotation_id=quotation_id,
            scope_type=term.scope_type,
            term_type=term.term_type,
            description=term.description,
            amount=term.amount,
        ))
    for term in terms.payment:
        session.add(QuotationPaymentTermModel(
            quotation_id=quotation_id,
            sequence=term.sequence,
            percentage=term.percentage,
            trigger_type=term.trigger_type,
            trigger_description=term.trigger_description,
        ))
    if terms.warranty is not None:
        session.add(QuotationWarrantyTermModel(
            quotation_id=quotation_id,
            period=terms.warranty.period,
            period_unit=terms.warranty.period_unit,
            extend_percent=terms.warranty.extend_percent,
            extend_period=terms.warranty.extend_period,
        ))
    session.flush()


def _item_ids_by_key(session: Session, quotation_id: int, slots: dict) -> dict[str, int]:
    rows = session.execute(
        select(QuotationPackageModel.sequence, WorkItemModel.sequence, WorkItemModel.item_id)
        .join(WorkItemModel, WorkItemModel.package_id == QuotationPackageModel.package_id)
        .where(QuotationPackageModel.quotation_id == quotation_id)
    ).all()
    by_position = {(package_seq, item_seq): item_id for package_seq, item_seq, item_id in rows}
    return {
        key: by_position[(slot.package_index + 1, slot.item_index + 1)]
        for key, slot in slots.items()
    }


def ingest_quotation(session: Session, file: QuotationFile, source_file: str) -> IngestResult:
    """Ghi cả công trình (báo giá, phát sinh, điều khoản, dự toán) rồi commit một lần.

    Lỗi bất kỳ sau khi bắt đầu ghi thì rollback toàn bộ và ném lại lỗi.
    """
    if session.execute(
        select(ProjectModel.project_id).where(ProjectModel.name == file.project.name)
    ).first() is not None:
        raise DuplicateProjectError(f"Đã có công trình tên {file.project.name!r}")

    knowledge, slots = to_knowledge(file, source_file)
    try:
        quotation: QuotationModel = SqlAlchemyQuotationRepository(session).persist(knowledge)
        item_ids = _item_ids_by_key(session, quotation.quotation_id, slots)

        write_terms(session, quotation.quotation_id, to_terms(file))

        extras = to_extra_quotations(file)
        extra_repository = SqlAlchemyExtraQuotationRepository(session)
        for extra in extras:
            extra_repository.save(quotation.project_id, extra)

        bundle = to_estimation_bundle(file, item_ids)
        if bundle is not None:
            SqlAlchemyEstimationRepository(session).create(quotation.project_id, bundle)

        session.commit()
    except Exception:
        logger.error("Ingest %r failed; rolling back", source_file, exc_info=True)
        session.rollback()
        raise

    return IngestResult(
        project_id=quotation.project_id,
        quotation_id=quotation.quotation_id,
        work_item_count=len(slots),
        has_estimation=bundle is not None,
        extra_count=len(extras),
    )
