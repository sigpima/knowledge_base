from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infrastructure.observability.logger import get_logger
from ..models import (
    ConceptModel,
    ProjectModel,
    QuotationModel,
    QuotationPackageModel,
    WorkItemModel,
    WorkStepModel,
)
from ....application.dto import (
    CreateConceptData,
    CreateQuotationPackageData,
    CreateWorkItemData,
    CreateWorkStepData,
    QuotationKnowledge,
)
from ....domain.entities import Quotation
from ....domain.repositories import QuotationRepository

logger = get_logger(__name__)

# Keys accepted by find_quotations' order_by param -> (QuotationModel column, descending).
_QUOTATION_ORDER_BY = {
    "issue_date_desc": (QuotationModel.issue_date, True),
    "issue_date_asc": (QuotationModel.issue_date, False),
    "total_amount_desc": (QuotationModel.total_amount, True),
    "total_amount_asc": (QuotationModel.total_amount, False),
}


def _effective_package_total(package: QuotationPackageModel) -> Decimal:
    """package.total_amount có thể để trống trong file YAML -- khi đó cộng
    total_price các hạng mục để người gọi (và agent) nhận số thật thay vì NULL."""
    if package.total_amount is not None:
        return package.total_amount
    return sum(
        (wi.total_price for wi in package.work_items if wi.total_price is not None),
        Decimal("0"),
    )


def _effective_quotation_total(quotation: QuotationModel) -> Decimal:
    """quotation.total_amount có thể là NULL -- khi đó cộng tổng các gói
    để NULL không bao giờ hiện ra thành số 0 trơ trụi."""
    if quotation.total_amount is not None:
        return quotation.total_amount
    return sum(
        (_effective_package_total(p) for p in quotation.packages),
        Decimal("0"),
    )


class SqlAlchemyQuotationRepository(QuotationRepository):

    def __init__(self, session: Session):
        self.session = session
        # Per-call cache to avoid redundant SELECTs for concepts that repeat
        # across work items within one persist().
        self._concept_cache: dict[tuple[str, str], ConceptModel] = {}

    # -- QuotationRepository port -------------------------------------------

    def get_by_id(self, quotation_id: int) -> Quotation:
        raise NotImplementedError(
            "Reading the full quotation -> package -> work_item graph "
            "is not implemented yet."
        )

    def save(self, quotation: Quotation) -> None:
        raise NotImplementedError(
            "Writing a Quotation aggregate through this port is not implemented yet; "
            "use persist() for the ingest write path."
        )

    # -- Ingestion write (full project/quotation/package/work_item aggregate) --

    def persist(self, knowledge: QuotationKnowledge) -> QuotationModel:
        try:
            project = ProjectModel(
                name=knowledge.project.name,
                address=knowledge.project.address,
                source_file=knowledge.project.source_file,
                created_at=date.today(),
                estimated_workdays=knowledge.project.estimated_workdays,
            )
            self.session.add(project)
            self.session.flush()

            quotation_data = knowledge.quotation
            quotation = QuotationModel(
                quotation_code=quotation_data.quotation_code,
                project_id=project.project_id,
                issue_date=quotation_data.issue_date,
                total_amount=quotation_data.total_amount,
                currency=quotation_data.currency,
                extra_metadata=quotation_data.metadata,
            )
            self.session.add(quotation)
            self.session.flush()

            for package_data in quotation_data.packages:
                self._persist_package(quotation=quotation, data=package_data)

            self.session.flush()
            return quotation
        except Exception:
            logger.error("Failed to persist quotation %r", knowledge.quotation.quotation_code, exc_info=True)
            self.session.rollback()
            raise

    def _persist_package(
        self,
        quotation: QuotationModel,
        data: CreateQuotationPackageData,
    ) -> QuotationPackageModel:

        package = QuotationPackageModel(
            quotation_id=quotation.quotation_id,
            name=data.name,
            sequence=data.sequence,
            total_amount=data.total_amount,
        )
        self.session.add(package)
        self.session.flush()

        for sequence, work_item_data in enumerate(data.work_items, start=1):
            self._persist_work_item(package=package, sequence=sequence, data=work_item_data)

        return package

    def _persist_work_item(
        self,
        package: QuotationPackageModel,
        sequence: int,
        data: CreateWorkItemData,
    ) -> WorkItemModel:

        total_price = (
            data.unit_price * data.quantity
            if data.unit_price is not None and data.quantity is not None
            else None
        )

        work_item = WorkItemModel(
            package_id=package.package_id,
            sequence=sequence,
            name=data.name,
            description=data.description,
            quantity=data.quantity,
            unit=data.unit,
            unit_price=data.unit_price,
            total_price=total_price,
            currency=data.currency,
        )
        self.session.add(work_item)
        self.session.flush()

        for sequence, step_data in enumerate(data.work_steps, start=1):
            self._persist_work_step(work_item=work_item, sequence=sequence, data=step_data)

        for concept_data in data.concepts:
            concept = self._get_or_create_concept(concept_data)
            work_item.concepts.append(concept)

        return work_item

    def _persist_work_step(
        self,
        work_item: WorkItemModel,
        sequence: int,
        data: CreateWorkStepData,
    ) -> WorkStepModel:

        # WorkStepModel has no "name" column -- the step's title is stored in
        # `description`.
        step = WorkStepModel(
            item_id=work_item.item_id,
            sequence=sequence,
            layers=data.layers,
            description=data.name,
            note=data.note,
            product_name=data.product_name,
        )
        self.session.add(step)
        self.session.flush()

        return step

    def _get_or_create_concept(self, data: CreateConceptData) -> ConceptModel:
        key = (data.type, data.name)
        if key in self._concept_cache:
            return self._concept_cache[key]

        concept = (
            self.session.query(ConceptModel)
            .filter(ConceptModel.type == data.type, ConceptModel.name == data.name)
            .one_or_none()
        )
        if concept is None:
            concept = ConceptModel(type=data.type, name=data.name)
            self.session.add(concept)
            self.session.flush()

        self._concept_cache[key] = concept
        return concept

    # -- Read / summary queries ----------------------------------------------

    def summarize_quotation(self, quotation_id: int) -> dict | None:
        quotation = self.session.get(QuotationModel, quotation_id)
        if quotation is None:
            return None

        num_packages = len(quotation.packages)
        num_work_items = sum(len(package.work_items) for package in quotation.packages)

        return {
            "quotation_id": quotation.quotation_id,
            "quotation_code": quotation.quotation_code,
            "project_name": quotation.project.name,
            "num_packages": num_packages,
            "num_work_items": num_work_items,
            "total_amount": _effective_quotation_total(quotation),
        }

    def _to_detail_dict(self, quotation: QuotationModel) -> dict:
        return {
            "quotation_id": quotation.quotation_id,
            "quotation_code": quotation.quotation_code,
            "project_id": quotation.project_id,
            "project_name": quotation.project.name,
            "issue_date": quotation.issue_date,
            "currency": quotation.currency,
            "total_amount": _effective_quotation_total(quotation),
            "packages": [
                {
                    "package_id": package.package_id,
                    "name": package.name,
                    "total_amount": _effective_package_total(package),
                    "work_items": [
                        {
                            "item_id": work_item.item_id,
                            "name": work_item.name,
                            "unit": work_item.unit,
                            "quantity": work_item.quantity,
                            "unit_price": work_item.unit_price,
                            "total_price": work_item.total_price,
                        }
                        for work_item in package.work_items
                    ],
                }
                for package in quotation.packages
            ],
        }

    def get_quotation_detail(self, quotation_id: int) -> dict | None:
        quotation = self.session.get(QuotationModel, quotation_id)
        if quotation is None:
            return None
        return self._to_detail_dict(quotation)

    def find_quotations(
        self,
        project_id: int | None,
        order_by: str,
        limit: int,
    ) -> tuple[list[dict], int] | None:
        """Filter/sort/limit quotations, returning full detail per match
        (same shape as get_quotation_detail) plus the true total match
        count. Returns None for an unrecognized `order_by` -- the caller
        (the MCP tool) surfaces that as a tool error rather than silently
        falling back to a default sort."""
        if order_by not in _QUOTATION_ORDER_BY:
            return None

        column, descending = _QUOTATION_ORDER_BY[order_by]

        filters = [QuotationModel.project_id == project_id] if project_id is not None else []

        matched_count = self.session.execute(
            select(func.count()).select_from(QuotationModel).where(*filters)
        ).scalar_one()

        # NULLS LAST regardless of direction: a NULL total_amount/issue_date
        # (dữ liệu có thể thiếu, ví dụ báo giá không khai issue_date) là
        # dữ liệu thiếu, không phải giá trị "thấp nhất" thật
        # value -- Postgres's DESC-sorts-NULLS-FIRST default would otherwise
        # surface it as the "highest total_amount" quotation.
        sort_column = column.desc() if descending else column.asc()
        order_stmt = (
            select(QuotationModel)
            .where(*filters)
            .order_by(sort_column.nulls_last())
            .limit(limit)
        )
        quotations = self.session.execute(order_stmt).scalars().all()

        return [self._to_detail_dict(q) for q in quotations], matched_count

    def summarize_project(self, project_id: int) -> dict | None:
        project = self.session.get(ProjectModel, project_id)
        if project is None:
            return None

        num_packages = 0
        num_work_items = 0
        total_amount = Decimal("0")
        for quotation in project.quotations:
            num_packages += len(quotation.packages)
            num_work_items += sum(len(p.work_items) for p in quotation.packages)
            total_amount += _effective_quotation_total(quotation)

        return {
            "project_id": project.project_id,
            "project_name": project.name,
            "num_quotations": len(project.quotations),
            "num_packages": num_packages,
            "num_work_items": num_work_items,
            "total_amount": total_amount,
        }
