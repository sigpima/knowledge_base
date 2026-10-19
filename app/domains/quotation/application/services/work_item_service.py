from dataclasses import dataclass, field
from decimal import Decimal
from difflib import SequenceMatcher

from sqlalchemy import and_
from sqlalchemy.orm import Session, joinedload

from ...domain.entities import WorkItem
from ...domain.repositories.work_item_repository import WorkItemRepository
from ...domain.value_objects.money import Money
from ...domain.value_objects.quantity import Quantity
from ...infrastructure.persistence.models import ConceptModel, QuotationModel, QuotationPackageModel, WorkItemModel
from ..dto import CreateConceptData, CreateWorkItemData, WorkItemData

# Loose enough to survive minor name formatting differences (numbering,
# spacing, wording order), tight enough to reject genuinely unrelated work items.
NAME_SIMILARITY_THRESHOLD = 0.4

# Keeps the response citable without letting a large match set balloon the
# tool result — matched_count still carries the true total.
MAX_MATCHED_ITEMS = 10


@dataclass
class MatchedWorkItem:
    item_id: int
    name: str
    project_name: str
    unit_price: Decimal
    name_similarity_score: float


@dataclass
class PriceAnalysis:
    matched_count: int
    historical_min: Decimal | None = None
    historical_max: Decimal | None = None
    historical_avg: Decimal | None = None
    pct_diff_from_avg: float | None = None
    matched_items: list[MatchedWorkItem] = field(default_factory=list)


class WorkItemApplicationService:

    def __init__(self, repository: WorkItemRepository | None = None, session: Session | None = None):
        # `repository` (a WorkItemRepository port) backs the CRUD methods below
        # and can be a fake in unit tests; `session` backs the price-comparison
        # methods, which need direct SQL (joinedload, similarity scoring across
        # every work item) that the narrow CRUD port doesn't expose. A caller
        # only needs to supply whichever collaborator its methods actually use.
        self.repository = repository
        self.session = session

    # -- Work item CRUD (via WorkItemRepository port) ------------------------

    def create(self, package_id: int, sequence: int, data: CreateWorkItemData) -> WorkItemData:
        work_item = WorkItem(
            package_id=package_id,
            sequence=sequence,
            name=data.name,
            description=data.description or "",
            quantity=Quantity(value=data.quantity, unit=data.unit),
            unit_price=Money(amount=data.unit_price, currency=data.currency),
        )

        saved = self.repository.save(work_item)

        return self._to_data(saved)

    def get(self, item_id: int) -> WorkItemData | None:
        work_item = self.repository.get_by_id(item_id)

        if work_item is None:
            return None

        return self._to_data(work_item)

    def _to_data(self, work_item: WorkItem) -> WorkItemData:
        return WorkItemData(
            item_id=work_item.item_id,
            name=work_item.name,
            sequence=work_item.sequence,
            description=work_item.description,
            quantity=work_item.quantity.value,
            unit=work_item.quantity.unit,
            unit_price=work_item.unit_price.amount,
            currency=work_item.unit_price.currency,
            total_price=work_item.total_price.amount,
        )

    # -- Historical price comparison (direct SQL query over every work item) --

    def compare_price_by_item_id(self, item_id: int) -> "PriceAnalysis | None":
        model = self.session.get(WorkItemModel, item_id)
        if model is None:
            return None

        # compare_price_by_item_id excludes the item being compared from its own
        # candidate pool, otherwise every item would trivially match itself.
        as_create_data = CreateWorkItemData(
            name=model.name,
            description=model.description,
            unit=model.unit,
            unit_price=model.unit_price,
            quantity=model.quantity,
            currency=model.currency,
            concepts=[CreateConceptData(type=c.type, name=c.name) for c in model.concepts],
        )
        return self.compare_price(as_create_data, exclude_item_id=model.item_id)

    def compare_price(self, work_item: CreateWorkItemData, exclude_item_id: int | None = None) -> PriceAnalysis:
        # Mỗi hạng mục có tối đa một concept loại `category` (xem docs/data-format.md),
        # nên lấy phần tử khớp đầu tiên là đúng, không phải đường tắt.
        category = next((c.name for c in work_item.concepts if c.type == "category"), None)
        if category is None:
            return PriceAnalysis(matched_count=0)

        # Unit compatibility can't be confirmed without a parsed unit, and mixing units (m2
        # rate vs. Gói lump sum) would silently corrupt the price averages below.
        if work_item.unit is None:
            return PriceAnalysis(matched_count=0)

        applications = [c.name for c in work_item.concepts if c.type == "application"]
        objects = [c.name for c in work_item.concepts if c.type == "object"]

        query = self.session.query(WorkItemModel).options(
            joinedload(WorkItemModel.quotation_package)
            .joinedload(QuotationPackageModel.quotation)
            .joinedload(QuotationModel.project)
        ).filter(
            WorkItemModel.unit_price.isnot(None),
            WorkItemModel.unit == work_item.unit,
            WorkItemModel.concepts.any(and_(ConceptModel.type == "category", ConceptModel.name == category)),
        )
        if exclude_item_id is not None:
            query = query.filter(WorkItemModel.item_id != exclude_item_id)
        for application in applications:
            query = query.filter(
                WorkItemModel.concepts.any(
                    and_(ConceptModel.type == "application", ConceptModel.name == application)
                )
            )
        if objects:
            query = query.filter(
                WorkItemModel.concepts.any(
                    and_(ConceptModel.type == "object", ConceptModel.name.in_(objects))
                )
            )

        candidates = query.all()
        if not candidates:
            return PriceAnalysis(matched_count=0)

        candidate_ratios = {
            candidate.item_id: SequenceMatcher(
                None, work_item.name.lower(), candidate.name.lower()
            ).ratio()
            for candidate in candidates
        }
        refined = [
            candidate
            for candidate in candidates
            if candidate_ratios[candidate.item_id] >= NAME_SIMILARITY_THRESHOLD
        ]
        # Falling back to the full concept-filtered group (rather than an empty result) is
        # deliberate: don't let name refinement erase all reference data when nothing clears
        # the similarity threshold.
        matched = refined if refined else candidates

        prices = [candidate.unit_price for candidate in matched]
        historical_min = min(prices)
        historical_max = max(prices)
        historical_avg = (sum(prices) / len(prices)).quantize(Decimal("0.01"))

        pct_diff_from_avg = None
        if work_item.unit_price is not None and historical_avg != 0:
            pct_diff_from_avg = float(round((work_item.unit_price - historical_avg) / historical_avg * 100, 1))

        scored = sorted(matched, key=lambda candidate: candidate_ratios[candidate.item_id], reverse=True)
        matched_items = [
            MatchedWorkItem(
                item_id=candidate.item_id,
                name=candidate.name,
                project_name=candidate.quotation_package.quotation.project.name,
                unit_price=candidate.unit_price,
                name_similarity_score=round(candidate_ratios[candidate.item_id], 4),
            )
            for candidate in scored[:MAX_MATCHED_ITEMS]
        ]

        return PriceAnalysis(
            matched_count=len(matched),
            historical_min=historical_min,
            historical_max=historical_max,
            historical_avg=historical_avg,
            pct_diff_from_avg=pct_diff_from_avg,
            matched_items=matched_items,
        )
