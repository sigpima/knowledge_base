from dataclasses import dataclass, field
from decimal import Decimal
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from ...domain.repositories.estimation_repository import EstimationRepository
from ...infrastructure.persistence.models import WorkItemModel
from ..dto import EstimationData, EstimationWorkItemData

# Stricter than WorkItemApplicationService.compare_price's 0.4: a false match here misreports
# two genuinely different materials/processes as "the same thing, changed" --
# a false non-match just falls back to two separate only_a/only_b entries,
# which is the safer failure for a diff tool.
MATERIAL_NAME_SIMILARITY_THRESHOLD = 0.5
PROCESS_NAME_SIMILARITY_THRESHOLD = 0.5


@dataclass
class MaterialSnapshot:
    product_name: str | None
    layers: int | None
    construction_loss: Decimal | None
    theoretical_rate: Decimal | None
    unit_price_per_m2: Decimal | None
    total_price_area_based: Decimal | None


@dataclass
class MaterialDiff:
    match_type: str
    name_similarity_score: float | None
    a: MaterialSnapshot | None
    b: MaterialSnapshot | None


@dataclass
class ProcessSnapshot:
    name: str
    main_labors_kn: int | None
    main_labors_out: int | None
    sub_labors_out: int | None
    days: Decimal | None
    kn_manday: Decimal | None
    main_out_manday: Decimal | None
    sub_out_manday: Decimal | None


@dataclass
class ProcessDiff:
    match_type: str
    name_similarity_score: float | None
    a: ProcessSnapshot | None
    b: ProcessSnapshot | None


@dataclass
class LaborInfoDiff:
    final_unit_price_type_a: str | None
    final_unit_price_type_b: str | None
    labor_coeff_a: Decimal | None
    labor_coeff_b: Decimal | None
    labor_coeff_diff: Decimal | None
    kn_manday_a: Decimal | None
    kn_manday_b: Decimal | None
    kn_manday_diff: Decimal | None
    main_out_manday_a: Decimal | None
    main_out_manday_b: Decimal | None
    main_out_manday_diff: Decimal | None
    sub_out_manday_a: Decimal | None
    sub_out_manday_b: Decimal | None
    sub_out_manday_diff: Decimal | None
    area_a: Decimal | None
    area_b: Decimal | None
    area_diff: Decimal | None


@dataclass
class EstimationDetailDiff:
    item_id_a: int
    item_id_b: int
    name_a: str
    name_b: str
    unit_price_a: Decimal | None
    unit_price_b: Decimal | None
    price_diff: Decimal | None
    price_diff_pct: Decimal | None
    material_unit_price_a: Decimal | None
    material_unit_price_b: Decimal | None
    material_unit_price_diff: Decimal | None
    labor_unit_price_a: Decimal | None
    labor_unit_price_b: Decimal | None
    labor_unit_price_diff: Decimal | None
    profit_margin_a: Decimal | None
    profit_margin_b: Decimal | None
    profit_margin_diff: Decimal | None
    labor_info_diff: LaborInfoDiff | None
    materials: list[MaterialDiff] = field(default_factory=list)
    processes: list[ProcessDiff] = field(default_factory=list)


def _diff(a: Decimal | None, b: Decimal | None) -> Decimal | None:
    if a is None or b is None:
        return None
    return b - a


def _greedy_match_indices(names_a: list[str], names_b: list[str], threshold: float):
    """Pairwise-score every (a, b) combination, then greedily claim the
    highest-scoring pairs first (no row claimed twice). Returns
    (matched_pairs, unmatched_a_indices, unmatched_b_indices), where
    matched_pairs is a list of (a_index, b_index, score) sorted by score
    descending."""
    scored_pairs = []
    for i, name_a in enumerate(names_a):
        for j, name_b in enumerate(names_b):
            score = SequenceMatcher(None, name_a.lower(), name_b.lower()).ratio()
            if score >= threshold:
                scored_pairs.append((score, i, j))
    scored_pairs.sort(key=lambda pair: pair[0], reverse=True)

    claimed_a: set[int] = set()
    claimed_b: set[int] = set()
    matched_pairs = []
    for score, i, j in scored_pairs:
        if i in claimed_a or j in claimed_b:
            continue
        claimed_a.add(i)
        claimed_b.add(j)
        matched_pairs.append((i, j, score))

    unmatched_a = [i for i in range(len(names_a)) if i not in claimed_a]
    unmatched_b = [j for j in range(len(names_b)) if j not in claimed_b]
    return matched_pairs, unmatched_a, unmatched_b


def _material_snapshot(material) -> MaterialSnapshot:
    return MaterialSnapshot(
        product_name=material.product_name,
        layers=material.layers,
        construction_loss=material.construction_loss,
        theoretical_rate=material.theoretical_rate,
        unit_price_per_m2=material.unit_price_per_m2,
        total_price_area_based=material.total_price_area_based,
    )


def _diff_materials(materials_a, materials_b) -> list[MaterialDiff]:
    names_a = [m.product_name or "" for m in materials_a]
    names_b = [m.product_name or "" for m in materials_b]
    matched_pairs, unmatched_a, unmatched_b = _greedy_match_indices(
        names_a, names_b, MATERIAL_NAME_SIMILARITY_THRESHOLD
    )

    result = [
        MaterialDiff(
            match_type="matched",
            name_similarity_score=round(score, 4),
            a=_material_snapshot(materials_a[i]),
            b=_material_snapshot(materials_b[j]),
        )
        for i, j, score in matched_pairs
    ]
    result += [
        MaterialDiff(match_type="only_a", name_similarity_score=None, a=_material_snapshot(materials_a[i]), b=None)
        for i in unmatched_a
    ]
    result += [
        MaterialDiff(match_type="only_b", name_similarity_score=None, a=None, b=_material_snapshot(materials_b[j]))
        for j in unmatched_b
    ]
    return result


def _process_snapshot(process) -> ProcessSnapshot:
    return ProcessSnapshot(
        name=process.name,
        main_labors_kn=process.main_labors_kn,
        main_labors_out=process.main_labors_out,
        sub_labors_out=process.sub_labors_out,
        days=process.days,
        kn_manday=process.kn_manday,
        main_out_manday=process.main_out_manday,
        sub_out_manday=process.sub_out_manday,
    )


def _diff_processes(processes_a, processes_b) -> list[ProcessDiff]:
    names_a = [p.name for p in processes_a]
    names_b = [p.name for p in processes_b]
    matched_pairs, unmatched_a, unmatched_b = _greedy_match_indices(
        names_a, names_b, PROCESS_NAME_SIMILARITY_THRESHOLD
    )

    result = [
        ProcessDiff(
            match_type="matched",
            name_similarity_score=round(score, 4),
            a=_process_snapshot(processes_a[i]),
            b=_process_snapshot(processes_b[j]),
        )
        for i, j, score in matched_pairs
    ]
    result += [
        ProcessDiff(match_type="only_a", name_similarity_score=None, a=_process_snapshot(processes_a[i]), b=None)
        for i in unmatched_a
    ]
    result += [
        ProcessDiff(match_type="only_b", name_similarity_score=None, a=None, b=_process_snapshot(processes_b[j]))
        for j in unmatched_b
    ]
    return result


class EstimationApplicationService:

    def __init__(self, repository: EstimationRepository | None = None, session: Session | None = None):
        # `repository` (an EstimationRepository port) backs the get_estimation/
        # get_estimation_work_item lookups below; `session` backs compare_detail,
        # which needs a direct WorkItemModel lookup the narrow port doesn't expose.
        self.repository = repository
        self.session = session

    # -- Dự toán lookup (via EstimationRepository port) -----------------------

    def get_estimation(self, project_id: int) -> EstimationData | None:
        return self.repository.get_by_project_id(project_id)

    def get_estimation_work_item(self, item_id: int) -> EstimationWorkItemData | None:
        return self.repository.get_work_item_detail(item_id)

    # -- Detail comparison (direct WorkItemModel lookup + repository) ---------

    def compare_detail(self, item_id_a: int, item_id_b: int) -> "EstimationDetailDiff | None":
        work_item_a = self.session.get(WorkItemModel, item_id_a)
        work_item_b = self.session.get(WorkItemModel, item_id_b)
        if work_item_a is None or work_item_b is None:
            return None

        detail_a = self.repository.get_work_item_detail(item_id_a)
        detail_b = self.repository.get_work_item_detail(item_id_b)
        if detail_a is None or detail_b is None:
            return None

        price_diff = _diff(work_item_a.unit_price, work_item_b.unit_price)
        price_diff_pct = None
        if price_diff is not None and work_item_a.unit_price:
            price_diff_pct = (price_diff / work_item_a.unit_price * 100).quantize(Decimal("0.01"))

        labor_info_diff = None
        if detail_a.labor_info is not None and detail_b.labor_info is not None:
            labor_info_diff = LaborInfoDiff(
                final_unit_price_type_a=detail_a.labor_info.final_unit_price_type,
                final_unit_price_type_b=detail_b.labor_info.final_unit_price_type,
                labor_coeff_a=detail_a.labor_info.labor_coeff,
                labor_coeff_b=detail_b.labor_info.labor_coeff,
                labor_coeff_diff=_diff(detail_a.labor_info.labor_coeff, detail_b.labor_info.labor_coeff),
                kn_manday_a=detail_a.labor_info.kn_manday,
                kn_manday_b=detail_b.labor_info.kn_manday,
                kn_manday_diff=_diff(detail_a.labor_info.kn_manday, detail_b.labor_info.kn_manday),
                main_out_manday_a=detail_a.labor_info.main_out_manday,
                main_out_manday_b=detail_b.labor_info.main_out_manday,
                main_out_manday_diff=_diff(detail_a.labor_info.main_out_manday, detail_b.labor_info.main_out_manday),
                sub_out_manday_a=detail_a.labor_info.sub_out_manday,
                sub_out_manday_b=detail_b.labor_info.sub_out_manday,
                sub_out_manday_diff=_diff(detail_a.labor_info.sub_out_manday, detail_b.labor_info.sub_out_manday),
                area_a=detail_a.labor_info.area,
                area_b=detail_b.labor_info.area,
                area_diff=_diff(detail_a.labor_info.area, detail_b.labor_info.area),
            )

        processes_a = detail_a.labor_info.processes if detail_a.labor_info is not None else []
        processes_b = detail_b.labor_info.processes if detail_b.labor_info is not None else []

        return EstimationDetailDiff(
            item_id_a=item_id_a,
            item_id_b=item_id_b,
            name_a=work_item_a.name,
            name_b=work_item_b.name,
            unit_price_a=work_item_a.unit_price,
            unit_price_b=work_item_b.unit_price,
            price_diff=price_diff,
            price_diff_pct=price_diff_pct,
            material_unit_price_a=detail_a.material_unit_price,
            material_unit_price_b=detail_b.material_unit_price,
            material_unit_price_diff=_diff(detail_a.material_unit_price, detail_b.material_unit_price),
            labor_unit_price_a=detail_a.labor_unit_price,
            labor_unit_price_b=detail_b.labor_unit_price,
            labor_unit_price_diff=_diff(detail_a.labor_unit_price, detail_b.labor_unit_price),
            profit_margin_a=detail_a.profit_margin,
            profit_margin_b=detail_b.profit_margin,
            profit_margin_diff=_diff(detail_a.profit_margin, detail_b.profit_margin),
            labor_info_diff=labor_info_diff,
            materials=_diff_materials(detail_a.main_materials, detail_b.main_materials),
            processes=_diff_processes(processes_a, processes_b),
        )
