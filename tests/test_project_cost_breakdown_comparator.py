from decimal import Decimal

from app.domains.quotation.infrastructure.persistence.models import (
    EstimationModel, ProjectModel, QuotationModel, TotalDetailModel,
)
from app.domains.quotation.application.services.project_service import (
    ProjectApplicationService,
)


def _seed_project_with_breakdown(db_session, suffix, quotation_total_amount, total_detail_rows):
    project = ProjectModel(name=f"Công trình {suffix}", address="Q1")
    db_session.add(project)
    db_session.flush()
    quotation = QuotationModel(
        quotation_code=f"Q-{suffix}", project_id=project.project_id, total_amount=quotation_total_amount,
    )
    db_session.add(quotation)
    db_session.flush()
    estimation = EstimationModel(project_id=project.project_id)
    db_session.add(estimation)
    db_session.flush()
    for detail_type, price in total_detail_rows:
        db_session.add(TotalDetailModel(
            estimation_id=estimation.estimation_id, type=detail_type, name=detail_type, price=price,
        ))
    db_session.commit()
    return project


def _seed_project_without_estimation(db_session, suffix):
    project = ProjectModel(name=f"Công trình {suffix}", address="Q1")
    db_session.add(project)
    db_session.commit()
    return project


def test_compare_returns_none_for_missing_project(db_session):
    comparator = ProjectApplicationService(db_session)
    assert comparator.compare_cost_breakdown(999999, "material") is None


def test_compare_returns_none_when_project_has_no_estimation(db_session):
    project = _seed_project_without_estimation(db_session, "A")
    comparator = ProjectApplicationService(db_session)
    assert comparator.compare_cost_breakdown(project.project_id, "material") is None


def test_compare_resolves_material_shorthand(db_session):
    project = _seed_project_with_breakdown(
        db_session, "A", Decimal("1000000"),
        [("vật tư chính", Decimal("400000")), ("vật tư phụ", Decimal("100000")), ("nhân công", Decimal("300000"))],
    )
    comparator = ProjectApplicationService(db_session)
    result = comparator.compare_cost_breakdown(project.project_id, "material")

    assert result.cost_type == "material"
    assert result.price == Decimal("500000")
    assert result.pct_of_total == Decimal("50.00")


def test_compare_resolves_labor_shorthand(db_session):
    project = _seed_project_with_breakdown(
        db_session, "A", Decimal("1000000"),
        [("vật tư chính", Decimal("400000")), ("nhân công", Decimal("300000"))],
    )
    comparator = ProjectApplicationService(db_session)
    result = comparator.compare_cost_breakdown(project.project_id, "labor")

    assert result.price == Decimal("300000")
    assert result.pct_of_total == Decimal("30.00")


def test_compare_resolves_raw_type_string(db_session):
    project = _seed_project_with_breakdown(
        db_session, "A", Decimal("1000000"),
        [("vật tư chính", Decimal("400000")), ("chi phí khác", Decimal("200000"))],
    )
    comparator = ProjectApplicationService(db_session)
    result = comparator.compare_cost_breakdown(project.project_id, "Chi Phí Khác")

    assert result.cost_type == "chi phí khác"
    assert result.price == Decimal("200000")
    assert result.pct_of_total == Decimal("20.00")


def test_compare_computes_avg_min_max_and_pct_point_diff(db_session):
    target = _seed_project_with_breakdown(
        db_session, "Target", Decimal("1000000"), [("nhân công", Decimal("300000"))],
    )
    _seed_project_with_breakdown(db_session, "Low", Decimal("1000000"), [("nhân công", Decimal("100000"))])
    _seed_project_with_breakdown(db_session, "High", Decimal("1000000"), [("nhân công", Decimal("500000"))])

    comparator = ProjectApplicationService(db_session)
    result = comparator.compare_cost_breakdown(target.project_id, "labor")

    assert result.matched_count == 2
    assert result.min_pct_of_total == Decimal("10.00")
    assert result.max_pct_of_total == Decimal("50.00")
    assert result.avg_pct_of_total == Decimal("30.00")
    assert result.pct_point_diff_from_avg == Decimal("0.00")


def test_candidate_with_no_matching_total_detail_contributes_zero_price(db_session):
    target = _seed_project_with_breakdown(
        db_session, "Target", Decimal("1000000"), [("nhân công", Decimal("300000"))],
    )
    _seed_project_with_breakdown(db_session, "NoLabor", Decimal("1000000"), [("vật tư chính", Decimal("400000"))])

    comparator = ProjectApplicationService(db_session)
    result = comparator.compare_cost_breakdown(target.project_id, "labor")

    assert result.matched_count == 1
    assert result.matched_projects[0].price == Decimal("0")
    assert result.matched_projects[0].pct_of_total == Decimal("0.00")


def test_candidate_with_zero_quotation_total_excluded_from_population_stats(db_session):
    target = _seed_project_with_breakdown(
        db_session, "Target", Decimal("1000000"), [("nhân công", Decimal("300000"))],
    )
    _seed_project_with_breakdown(db_session, "ZeroTotal", None, [("nhân công", Decimal("50000"))])

    comparator = ProjectApplicationService(db_session)
    result = comparator.compare_cost_breakdown(target.project_id, "labor")

    assert result.matched_count == 0
    assert result.matched_projects == []
    assert result.avg_pct_of_total is None


def test_matched_projects_capped_at_ten_with_true_matched_count(db_session):
    target = _seed_project_with_breakdown(
        db_session, "Target", Decimal("1000000"), [("nhân công", Decimal("300000"))],
    )
    for i in range(12):
        _seed_project_with_breakdown(
            db_session, f"C{i}", Decimal("1000000"), [("nhân công", Decimal("100000"))],
        )

    comparator = ProjectApplicationService(db_session)
    result = comparator.compare_cost_breakdown(target.project_id, "labor")

    assert result.matched_count == 12
    assert len(result.matched_projects) == 10


def test_unmatched_cost_type_yields_zero_everywhere(db_session):
    target = _seed_project_with_breakdown(
        db_session, "Target", Decimal("1000000"), [("vật tư chính", Decimal("400000"))],
    )
    _seed_project_with_breakdown(db_session, "Other", Decimal("1000000"), [("nhân công", Decimal("300000"))])

    comparator = ProjectApplicationService(db_session)
    result = comparator.compare_cost_breakdown(target.project_id, "không tồn tại")

    assert result.price == Decimal("0")
    assert result.pct_of_total == Decimal("0.00")
    assert result.avg_pct_of_total == Decimal("0.00")
