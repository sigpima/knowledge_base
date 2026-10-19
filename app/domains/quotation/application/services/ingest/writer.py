"""Ghi một file báo giá đã kiểm tra vào DB trong đúng một transaction.

Công trình được nhận diện bằng tên (duy nhất trong DB) và so sánh nội dung bằng `content_hash`:
- chưa có tên đó                   -> ghi mới (`created`)
- có rồi, cùng nội dung            -> không làm gì (`unchanged`), nên gửi lại file cũ là an toàn
- có rồi, nội dung khác            -> `DuplicateProjectError` (HTTP 409), trừ khi `on_conflict="replace"`
                                      thì xoá cây cũ và ghi cây mới trong cùng transaction (`replaced`)
"""
import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.quotation.infrastructure.persistence.models import (
    EstimationModel,
    EstimationWorkItemModel,
    ExtraQuotationModel,
    ItemSubModel,
    LaborInfoModel,
    LaborInfoProcessModel,
    MainMaterialModel,
    ProductToBuyModel,
    ProjectModel,
    QuotationModel,
    QuotationPackageModel,
    QuotationPaymentTermModel,
    QuotationScopeTermModel,
    QuotationWarrantyTermModel,
    SubMaterialModel,
    TotalDetailModel,
    WorkItemModel,
    WorkStepModel,
)
from app.domains.quotation.infrastructure.persistence.models.concept import association_table as work_item_concept
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
    """Đã có công trình cùng tên nhưng nội dung khác."""


OnConflict = Literal["error", "replace"]


@dataclass
class IngestResult:
    project_id: int
    quotation_id: int
    work_item_count: int
    has_estimation: bool
    extra_count: int
    status: Literal["created", "unchanged", "replaced"] = "created"


def _canonical(value: Any) -> Any:
    """Dạng chuẩn để băm: số thập phân bỏ số 0 thừa (95000.00 == 95000), ngày theo ISO."""
    if isinstance(value, BaseModel):
        return _canonical(value.model_dump())
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    return value


def content_hash(file: QuotationFile) -> str:
    """sha256 của nội dung đã kiểm tra, không phụ thuộc thứ tự khoá, khoảng trắng hay cách viết số."""
    canonical = json.dumps(_canonical(file), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _find_project(session: Session, name: str) -> ProjectModel | None:
    return session.execute(select(ProjectModel).where(ProjectModel.name == name)).scalar_one_or_none()


def delete_project_tree(session: Session, project_id: int) -> None:
    """Xoá một công trình cùng mọi bảng con (schema không dùng ON DELETE CASCADE). Concept dùng chung nên giữ lại."""
    quotation_ids = select(QuotationModel.quotation_id).where(QuotationModel.project_id == project_id)
    package_ids = select(QuotationPackageModel.package_id).where(QuotationPackageModel.quotation_id.in_(quotation_ids))
    item_ids = select(WorkItemModel.item_id).where(WorkItemModel.package_id.in_(package_ids))
    estimation_ids = select(EstimationModel.estimation_id).where(EstimationModel.project_id == project_id)
    cost_item_ids = select(EstimationWorkItemModel.cost_item_id).where(
        EstimationWorkItemModel.estimation_id.in_(estimation_ids)
    )
    labor_ids = select(LaborInfoModel.labor_id).where(LaborInfoModel.cost_item_id.in_(cost_item_ids))
    sub_ids = select(SubMaterialModel.sub_id).where(SubMaterialModel.project_id == project_id)

    for statement in (
        delete(ItemSubModel).where(or_(ItemSubModel.item_id.in_(item_ids), ItemSubModel.sub_id.in_(sub_ids))),
        delete(LaborInfoProcessModel).where(LaborInfoProcessModel.labor_id.in_(labor_ids)),
        delete(LaborInfoModel).where(LaborInfoModel.cost_item_id.in_(cost_item_ids)),
        delete(MainMaterialModel).where(MainMaterialModel.cost_item_id.in_(cost_item_ids)),
        delete(EstimationWorkItemModel).where(EstimationWorkItemModel.estimation_id.in_(estimation_ids)),
        delete(TotalDetailModel).where(TotalDetailModel.estimation_id.in_(estimation_ids)),
        delete(EstimationModel).where(EstimationModel.project_id == project_id),
        delete(SubMaterialModel).where(SubMaterialModel.project_id == project_id),
        delete(ProductToBuyModel).where(ProductToBuyModel.project_id == project_id),
        delete(ExtraQuotationModel).where(ExtraQuotationModel.project_id == project_id),
        delete(work_item_concept).where(work_item_concept.c.item_id.in_(item_ids)),
        delete(WorkStepModel).where(WorkStepModel.item_id.in_(item_ids)),
        delete(WorkItemModel).where(WorkItemModel.package_id.in_(package_ids)),
        delete(QuotationPackageModel).where(QuotationPackageModel.quotation_id.in_(quotation_ids)),
        delete(QuotationPaymentTermModel).where(QuotationPaymentTermModel.quotation_id.in_(quotation_ids)),
        delete(QuotationScopeTermModel).where(QuotationScopeTermModel.quotation_id.in_(quotation_ids)),
        delete(QuotationWarrantyTermModel).where(QuotationWarrantyTermModel.quotation_id.in_(quotation_ids)),
        delete(QuotationModel).where(QuotationModel.project_id == project_id),
        delete(ProjectModel).where(ProjectModel.project_id == project_id),
    ):
        session.execute(statement)
    session.expire_all()


def _summary(session: Session, project: ProjectModel, status: str) -> IngestResult:
    """Tóm tắt một công trình đã có trong DB (dùng cho `unchanged`)."""
    quotation_id = session.execute(
        select(QuotationModel.quotation_id).where(QuotationModel.project_id == project.project_id)
    ).scalars().first()
    work_items = session.execute(
        select(func.count())
        .select_from(WorkItemModel)
        .join(QuotationPackageModel, QuotationPackageModel.package_id == WorkItemModel.package_id)
        .where(QuotationPackageModel.quotation_id == quotation_id)
    ).scalar_one()
    extras = session.execute(
        select(func.count()).select_from(ExtraQuotationModel).where(ExtraQuotationModel.project_id == project.project_id)
    ).scalar_one()
    has_estimation = session.execute(
        select(EstimationModel.estimation_id).where(EstimationModel.project_id == project.project_id)
    ).first() is not None
    return IngestResult(project.project_id, quotation_id, work_items, has_estimation, extras, status)


def _conflict_message(name: str) -> str:
    return (
        f"Đã có công trình tên {name!r} với nội dung khác. Muốn thay thế, gửi lại với "
        "on_conflict=replace (HTTP) hoặc --replace (CLI)."
    )


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


def ingest_quotation(
    session: Session, file: QuotationFile, source_file: str, on_conflict: OnConflict = "error"
) -> IngestResult:
    """Ghi cả công trình (báo giá, phát sinh, điều khoản, dự toán) rồi commit một lần.

    Lỗi bất kỳ sau khi bắt đầu ghi thì rollback toàn bộ (kể cả bước xoá khi `replace`) và ném lại lỗi.
    """
    name = file.project.name
    digest = content_hash(file)
    existing = _find_project(session, name)
    status = "created"
    if existing is not None:
        if existing.content_hash == digest:
            return _summary(session, existing, "unchanged")
        if on_conflict != "replace":
            raise DuplicateProjectError(_conflict_message(name))
        status = "replaced"
        replaced_project_id = existing.project_id

    knowledge, slots = to_knowledge(file, source_file)
    try:
        if status == "replaced":
            delete_project_tree(session, replaced_project_id)
        quotation: QuotationModel = SqlAlchemyQuotationRepository(session).persist(knowledge)
        session.get(ProjectModel, quotation.project_id).content_hash = digest
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
    except IntegrityError:
        # Hai request cùng tên chạy đồng thời: ràng buộc UNIQUE của DB chặn request đến sau.
        session.rollback()
        winner = _find_project(session, name)
        if winner is None:
            raise
        if winner.content_hash == digest:
            return _summary(session, winner, "unchanged")
        raise DuplicateProjectError(_conflict_message(name))
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
        status=status,
    )
