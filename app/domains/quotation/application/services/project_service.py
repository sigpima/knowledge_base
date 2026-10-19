from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from ...infrastructure.persistence.models import (
    ConceptModel, EstimationModel, EstimationWorkItemModel, LaborInfoModel,
    ProjectModel, QuotationModel, QuotationPackageModel, TotalDetailModel, WorkItemModel,
)
from ...infrastructure.persistence.repositories.estimation_repository import (
    LABOR_TOTAL_DETAIL_TYPES,
    MATERIAL_TOTAL_DETAIL_TYPES,
)

# Fixed 50/50 split between area closeness and hạng mục/concept overlap --
# not a tool parameter, keeps the tool's contract simple (one project in,
# one ranked comparison out).
AREA_WEIGHT = Decimal("0.5")
CONCEPT_WEIGHT = Decimal("0.5")

# Same shape as work_item_service.MAX_MATCHED_ITEMS: keeps the
# response citable without letting a large match set balloon the tool
# result -- matched_count still carries the true total.
MAX_MATCHED_PROJECTS = 10


@dataclass
class MatchedProject:
    project_id: int
    name: str
    total_out_cost: Decimal
    total_area: Decimal
    cost_diff: Decimal
    cost_diff_pct: Decimal | None
    similarity_score: float


@dataclass
class ProjectLaborCostComparison:
    project_id: int
    project_name: str
    total_out_cost: Decimal
    total_area: Decimal
    matched_count: int
    matched_projects: list[MatchedProject] = field(default_factory=list)


@dataclass
class MatchedProjectCostShare:
    project_id: int
    name: str
    price: Decimal
    pct_of_total: Decimal | None


@dataclass
class CostBreakdownComparison:
    project_id: int
    project_name: str
    cost_type: str
    price: Decimal
    quotation_total_amount: Decimal
    pct_of_total: Decimal | None
    matched_count: int
    avg_pct_of_total: Decimal | None
    min_pct_of_total: Decimal | None
    max_pct_of_total: Decimal | None
    pct_point_diff_from_avg: Decimal | None
    matched_projects: list[MatchedProjectCostShare] = field(default_factory=list)


class ProjectApplicationService:

    def __init__(self, session: Session):
        self.session = session

    # -- Cross-project labor cost comparison ----------------------------------

    def compare_labor_cost(self, project_id: int) -> "ProjectLaborCostComparison | None":
        target = self.session.get(ProjectModel, project_id)
        if target is None:
            return None

        target_estimation = (
            self.session.query(EstimationModel)
            .filter(EstimationModel.project_id == project_id)
            .one_or_none()
        )
        if target_estimation is None:
            return None

        # Batched per-project cost/area totals -- LEFT OUTER JOIN so a project
        # whose Estimation has no rows at all (or no LaborInfo rows) still
        # appears with 0s, rather than vanishing from the candidate pool.
        cost_area_rows = (
            self.session.query(
                EstimationModel.project_id,
                func.coalesce(func.sum(LaborInfoModel.main_out_total_price), 0),
                func.coalesce(func.sum(LaborInfoModel.sub_out_total_price), 0),
                func.coalesce(func.sum(LaborInfoModel.area), 0),
            )
            .outerjoin(EstimationWorkItemModel, EstimationWorkItemModel.estimation_id == EstimationModel.estimation_id)
            .outerjoin(LaborInfoModel, LaborInfoModel.cost_item_id == EstimationWorkItemModel.cost_item_id)
            .group_by(EstimationModel.project_id)
            .all()
        )
        cost_area_by_project = {
            pid: (main_out + sub_out, area)
            for pid, main_out, sub_out, area in cost_area_rows
        }

        target_out_cost, target_area = cost_area_by_project[project_id]
        candidate_project_ids = [pid for pid in cost_area_by_project if pid != project_id]
        matched_count = len(candidate_project_ids)

        if not candidate_project_ids:
            return ProjectLaborCostComparison(
                project_id=project_id,
                project_name=target.name,
                total_out_cost=target_out_cost,
                total_area=target_area,
                matched_count=0,
                matched_projects=[],
            )

        name_by_project = dict(
            self.session.query(ProjectModel.project_id, ProjectModel.name)
            .filter(ProjectModel.project_id.in_(candidate_project_ids))
            .all()
        )

        concept_rows = (
            self.session.query(QuotationModel.project_id, ConceptModel.type, ConceptModel.name)
            .select_from(WorkItemModel)
            .join(WorkItemModel.concepts)
            .join(WorkItemModel.quotation_package)
            .join(QuotationPackageModel.quotation)
            .filter(QuotationModel.project_id.in_(candidate_project_ids + [project_id]))
            .distinct()
            .all()
        )
        concept_sets: dict[int, set[tuple[str, str]]] = defaultdict(set)
        for pid, concept_type, concept_name in concept_rows:
            concept_sets[pid].add((concept_type, concept_name))
        target_concepts = concept_sets.get(project_id, set())

        scored: list[tuple[Decimal, MatchedProject]] = []
        for candidate_id in candidate_project_ids:
            candidate_out_cost, candidate_area = cost_area_by_project[candidate_id]
            candidate_concepts = concept_sets.get(candidate_id, set())

            if target_area == 0 and candidate_area == 0:
                area_similarity = Decimal("1")
            else:
                area_similarity = Decimal("1") - min(
                    Decimal("1"),
                    abs(target_area - candidate_area) / max(target_area, candidate_area),
                )

            union = target_concepts | candidate_concepts
            concept_similarity = (
                Decimal(len(target_concepts & candidate_concepts)) / Decimal(len(union))
                if union else Decimal("0")
            )

            score = AREA_WEIGHT * area_similarity + CONCEPT_WEIGHT * concept_similarity

            cost_diff = candidate_out_cost - target_out_cost
            cost_diff_pct = None
            if target_out_cost:
                cost_diff_pct = (cost_diff / target_out_cost * 100).quantize(Decimal("0.01"))

            scored.append((
                score,
                MatchedProject(
                    project_id=candidate_id,
                    name=name_by_project[candidate_id],
                    total_out_cost=candidate_out_cost,
                    total_area=candidate_area,
                    cost_diff=cost_diff,
                    cost_diff_pct=cost_diff_pct,
                    similarity_score=round(float(score), 4),
                ),
            ))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        matched_projects = [item for _, item in scored[:MAX_MATCHED_PROJECTS]]

        return ProjectLaborCostComparison(
            project_id=project_id,
            project_name=target.name,
            total_out_cost=target_out_cost,
            total_area=target_area,
            matched_count=matched_count,
            matched_projects=matched_projects,
        )

    # -- Cross-project cost-breakdown (% of total) comparison -----------------

    def compare_cost_breakdown(self, project_id: int, cost_type: str) -> "CostBreakdownComparison | None":
        target = self.session.get(ProjectModel, project_id)
        if target is None:
            return None

        estimation_project_ids = {
            pid for (pid,) in self.session.query(EstimationModel.project_id).all()
        }
        if project_id not in estimation_project_ids:
            return None

        quotation_totals = dict(
            self.session.query(QuotationModel.project_id, func.coalesce(func.sum(QuotationModel.total_amount), 0))
            .group_by(QuotationModel.project_id)
            .all()
        )

        detail_rows = (
            self.session.query(EstimationModel.project_id, TotalDetailModel.type, TotalDetailModel.price)
            .join(TotalDetailModel, TotalDetailModel.estimation_id == EstimationModel.estimation_id)
            .all()
        )
        details_by_project: dict[int, list[tuple[str, Decimal]]] = {}
        for pid, detail_type, price in detail_rows:
            details_by_project.setdefault(pid, []).append((detail_type, price))

        normalized = cost_type.strip().lower()
        if normalized == "material":
            match_set = MATERIAL_TOTAL_DETAIL_TYPES
        elif normalized == "labor":
            match_set = LABOR_TOTAL_DETAIL_TYPES
        else:
            match_set = {normalized}

        def price_for(pid: int) -> Decimal:
            return sum(
                (
                    price for detail_type, price in details_by_project.get(pid, [])
                    if detail_type.strip().lower() in match_set
                ),
                Decimal("0"),
            )

        def pct_for(pid: int, price: Decimal) -> Decimal | None:
            total = quotation_totals.get(pid, Decimal("0"))
            if not total:
                return None
            return (price / total * 100).quantize(Decimal("0.01"))

        name_by_project = dict(
            self.session.query(ProjectModel.project_id, ProjectModel.name)
            .filter(ProjectModel.project_id.in_(estimation_project_ids))
            .all()
        )

        target_price = price_for(project_id)
        target_pct = pct_for(project_id, target_price)

        candidate_ids = [pid for pid in estimation_project_ids if pid != project_id]
        scored = []
        for pid in candidate_ids:
            price = price_for(pid)
            pct = pct_for(pid, price)
            if pct is None:
                continue
            scored.append((pid, price, pct))

        matched_count = len(scored)
        pct_values = [pct for _, _, pct in scored]
        avg_pct = (sum(pct_values) / len(pct_values)).quantize(Decimal("0.01")) if pct_values else None
        min_pct = min(pct_values) if pct_values else None
        max_pct = max(pct_values) if pct_values else None
        pct_point_diff_from_avg = None
        if target_pct is not None and avg_pct is not None:
            pct_point_diff_from_avg = (target_pct - avg_pct).quantize(Decimal("0.01"))

        scored.sort(key=lambda item: item[2], reverse=True)
        matched_projects = [
            MatchedProjectCostShare(project_id=pid, name=name_by_project[pid], price=price, pct_of_total=pct)
            for pid, price, pct in scored[:MAX_MATCHED_PROJECTS]
        ]

        return CostBreakdownComparison(
            project_id=project_id,
            project_name=target.name,
            cost_type=normalized,
            price=target_price,
            quotation_total_amount=quotation_totals.get(project_id, Decimal("0")),
            pct_of_total=target_pct,
            matched_count=matched_count,
            avg_pct_of_total=avg_pct,
            min_pct_of_total=min_pct,
            max_pct_of_total=max_pct,
            pct_point_diff_from_avg=pct_point_diff_from_avg,
            matched_projects=matched_projects,
        )
