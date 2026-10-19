from decimal import Decimal

from app.domains.quotation.infrastructure.persistence.models import (
    ConceptModel, EstimationModel, EstimationWorkItemModel, LaborInfoModel,
    ProjectModel, QuotationModel, QuotationPackageModel, WorkItemModel,
)
from app.domains.quotation.application.services.project_service import (
    ProjectApplicationService,
)


def _make_project(db_session, name, address="Q1"):
    project = ProjectModel(name=name, address=address)
    db_session.add(project)
    db_session.flush()
    return project


def _make_estimation(db_session, project):
    estimation = EstimationModel(project_id=project.project_id)
    db_session.add(estimation)
    db_session.flush()
    return estimation


def _make_work_item_with_concepts(db_session, project, concept_names, sequence=1):
    quotation = QuotationModel(quotation_code=f"Q-{project.project_id}-{sequence}", project_id=project.project_id)
    db_session.add(quotation)
    db_session.flush()
    package = QuotationPackageModel(quotation_id=quotation.quotation_id, name="Gói I", sequence=1)
    db_session.add(package)
    db_session.flush()

    concepts = []
    for concept_type, concept_name in concept_names:
        concept = (
            db_session.query(ConceptModel)
            .filter(ConceptModel.type == concept_type, ConceptModel.name == concept_name)
            .one_or_none()
        )
        if concept is None:
            concept = ConceptModel(type=concept_type, name=concept_name)
            db_session.add(concept)
            db_session.flush()
        concepts.append(concept)

    work_item = WorkItemModel(
        package_id=package.package_id, sequence=sequence, name=f"Hạng mục {sequence}",
        currency="VND", concepts=concepts,
    )
    db_session.add(work_item)
    db_session.commit()
    return work_item


def _add_labor_cost_item(db_session, estimation, work_item, area, main_out_manday, main_out_total_price,
                          sub_out_manday=None, sub_out_total_price=None):
    cost_item = EstimationWorkItemModel(
        estimation_id=estimation.estimation_id, item_id=work_item.item_id if work_item else None,
        name="Hạng mục dự toán",
    )
    db_session.add(cost_item)
    db_session.flush()
    db_session.add(LaborInfoModel(
        cost_item_id=cost_item.cost_item_id, area=area,
        main_out_manday=main_out_manday, main_out_total_price=main_out_total_price,
        sub_out_manday=sub_out_manday, sub_out_total_price=sub_out_total_price,
    ))
    db_session.commit()
    return cost_item


def test_compare_returns_none_for_missing_project(db_session):
    comparator = ProjectApplicationService(db_session)
    assert comparator.compare_labor_cost(999999) is None


def test_compare_returns_none_when_project_has_no_estimation(db_session):
    project = _make_project(db_session, "Nhà không có dự toán")
    db_session.commit()

    comparator = ProjectApplicationService(db_session)
    assert comparator.compare_labor_cost(project.project_id) is None


def test_compare_returns_zero_matched_when_no_other_projects_have_estimation(db_session):
    project = _make_project(db_session, "Nhà một mình")
    estimation = _make_estimation(db_session, project)
    item = _make_work_item_with_concepts(db_session, project, [("category", "Sơn nước")])
    _add_labor_cost_item(db_session, estimation, item, area=Decimal("100"),
                          main_out_manday=Decimal("5"), main_out_total_price=Decimal("1000000"))

    comparator = ProjectApplicationService(db_session)
    result = comparator.compare_labor_cost(project.project_id)

    assert result is not None
    assert result.project_name == "Nhà một mình"
    assert result.total_out_cost == Decimal("1000000")
    assert result.total_area == Decimal("100")
    assert result.matched_count == 0
    assert result.matched_projects == []


def test_matched_projects_ordered_by_weighted_similarity_score(db_session):
    target = _make_project(db_session, "Công trình gốc")
    target_estimation = _make_estimation(db_session, target)
    target_item = _make_work_item_with_concepts(db_session, target, [("category", "Sơn nước"), ("application", "Nội thất")])
    _add_labor_cost_item(db_session, target_estimation, target_item, area=Decimal("100"),
                          main_out_manday=Decimal("5"), main_out_total_price=Decimal("1000000"))

    # close_match: same area, same concepts -> highest score.
    close = _make_project(db_session, "Công trình gần giống")
    close_estimation = _make_estimation(db_session, close)
    close_item = _make_work_item_with_concepts(db_session, close, [("category", "Sơn nước"), ("application", "Nội thất")])
    _add_labor_cost_item(db_session, close_estimation, close_item, area=Decimal("105"),
                          main_out_manday=Decimal("6"), main_out_total_price=Decimal("1200000"))

    # far_match: very different area, no shared concepts -> lowest score.
    far = _make_project(db_session, "Công trình khác hẳn")
    far_estimation = _make_estimation(db_session, far)
    far_item = _make_work_item_with_concepts(db_session, far, [("category", "Chống thấm")])
    _add_labor_cost_item(db_session, far_estimation, far_item, area=Decimal("2000"),
                          main_out_manday=Decimal("20"), main_out_total_price=Decimal("5000000"))

    comparator = ProjectApplicationService(db_session)
    result = comparator.compare_labor_cost(target.project_id)

    assert result.matched_count == 2
    matched_ids = [m.project_id for m in result.matched_projects]
    assert matched_ids == [close.project_id, far.project_id]
    assert result.matched_projects[0].similarity_score > result.matched_projects[1].similarity_score


def test_cost_diff_and_cost_diff_pct_computed_correctly(db_session):
    target = _make_project(db_session, "Công trình A")
    target_estimation = _make_estimation(db_session, target)
    target_item = _make_work_item_with_concepts(db_session, target, [("category", "Sơn nước")])
    _add_labor_cost_item(db_session, target_estimation, target_item, area=Decimal("100"),
                          main_out_manday=Decimal("5"), main_out_total_price=Decimal("1000000"),
                          sub_out_manday=Decimal("2"), sub_out_total_price=Decimal("200000"))

    other = _make_project(db_session, "Công trình B")
    other_estimation = _make_estimation(db_session, other)
    other_item = _make_work_item_with_concepts(db_session, other, [("category", "Sơn nước")])
    _add_labor_cost_item(db_session, other_estimation, other_item, area=Decimal("100"),
                          main_out_manday=Decimal("5"), main_out_total_price=Decimal("1500000"),
                          sub_out_manday=Decimal("2"), sub_out_total_price=Decimal("300000"))

    comparator = ProjectApplicationService(db_session)
    result = comparator.compare_labor_cost(target.project_id)

    assert result.total_out_cost == Decimal("1200000")
    matched = result.matched_projects[0]
    assert matched.project_id == other.project_id
    assert matched.total_out_cost == Decimal("1800000")
    assert matched.cost_diff == Decimal("600000")
    assert matched.cost_diff_pct == Decimal("50.00")


def test_cost_diff_pct_is_none_when_target_cost_is_zero(db_session):
    target = _make_project(db_session, "Công trình chi phí 0")
    target_estimation = _make_estimation(db_session, target)
    target_item = _make_work_item_with_concepts(db_session, target, [("category", "Sơn nước")])
    _add_labor_cost_item(db_session, target_estimation, target_item, area=Decimal("100"),
                          main_out_manday=None, main_out_total_price=None)

    other = _make_project(db_session, "Công trình khác")
    other_estimation = _make_estimation(db_session, other)
    other_item = _make_work_item_with_concepts(db_session, other, [("category", "Sơn nước")])
    _add_labor_cost_item(db_session, other_estimation, other_item, area=Decimal("100"),
                          main_out_manday=Decimal("5"), main_out_total_price=Decimal("1000000"))

    comparator = ProjectApplicationService(db_session)
    result = comparator.compare_labor_cost(target.project_id)

    assert result.total_out_cost == Decimal("0")
    assert result.matched_projects[0].cost_diff_pct is None


def test_candidate_without_estimation_excluded_from_matched_count(db_session):
    target = _make_project(db_session, "Công trình có dự toán")
    target_estimation = _make_estimation(db_session, target)
    target_item = _make_work_item_with_concepts(db_session, target, [("category", "Sơn nước")])
    _add_labor_cost_item(db_session, target_estimation, target_item, area=Decimal("100"),
                          main_out_manday=Decimal("5"), main_out_total_price=Decimal("1000000"))

    # No Estimation row for this project at all.
    _make_project(db_session, "Công trình không có dự toán")
    db_session.commit()

    comparator = ProjectApplicationService(db_session)
    result = comparator.compare_labor_cost(target.project_id)

    assert result.matched_count == 0
    assert result.matched_projects == []


def test_area_similarity_is_one_when_both_areas_zero(db_session):
    target = _make_project(db_session, "Công trình không diện tích A")
    target_estimation = _make_estimation(db_session, target)
    target_item = _make_work_item_with_concepts(db_session, target, [("category", "Sơn nước")])
    _add_labor_cost_item(db_session, target_estimation, target_item, area=None,
                          main_out_manday=Decimal("5"), main_out_total_price=Decimal("1000000"))

    other = _make_project(db_session, "Công trình không diện tích B")
    other_estimation = _make_estimation(db_session, other)
    other_item = _make_work_item_with_concepts(db_session, other, [("category", "Chống thấm")])
    _add_labor_cost_item(db_session, other_estimation, other_item, area=None,
                          main_out_manday=Decimal("3"), main_out_total_price=Decimal("600000"))

    comparator = ProjectApplicationService(db_session)
    result = comparator.compare_labor_cost(target.project_id)

    # Both areas are 0 (no area data) and no shared concepts -> score is exactly
    # the area-similarity half of the weight (0.5 * 1.0 + 0.5 * 0.0 == 0.5).
    assert result.matched_projects[0].similarity_score == 0.5


def test_matched_projects_capped_at_ten_with_true_matched_count(db_session):
    target = _make_project(db_session, "Công trình gốc nhiều đối chiếu")
    target_estimation = _make_estimation(db_session, target)
    target_item = _make_work_item_with_concepts(db_session, target, [("category", "Sơn nước")])
    _add_labor_cost_item(db_session, target_estimation, target_item, area=Decimal("100"),
                          main_out_manday=Decimal("5"), main_out_total_price=Decimal("1000000"))

    for i in range(12):
        candidate = _make_project(db_session, f"Công trình đối chiếu {i}")
        candidate_estimation = _make_estimation(db_session, candidate)
        candidate_item = _make_work_item_with_concepts(
            db_session, candidate, [("category", "Sơn nước")], sequence=i + 1,
        )
        _add_labor_cost_item(db_session, candidate_estimation, candidate_item, area=Decimal("100"),
                              main_out_manday=Decimal("5"), main_out_total_price=Decimal("1000000"))

    comparator = ProjectApplicationService(db_session)
    result = comparator.compare_labor_cost(target.project_id)

    assert result.matched_count == 12
    assert len(result.matched_projects) == 10
