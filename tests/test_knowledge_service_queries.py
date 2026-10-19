from datetime import date
from decimal import Decimal

from app.core.services.knowledge_service import KnowledgeService
from app.domains.quotation.infrastructure.persistence.models import (
    ConceptModel,
    EstimationModel,
    EstimationWorkItemModel,
    LaborInfoModel,
    ProjectModel,
    QuotationModel,
    QuotationPackageModel,
    TotalDetailModel,
    WorkItemModel,
)


def _seed(db_session):
    project = ProjectModel(name="Nhà chị Hai", address="Q7")
    db_session.add(project)
    db_session.flush()

    quotation = QuotationModel(
        quotation_code="Q-100",
        project_id=project.project_id,
        total_amount=500_000,
        currency="VND",
        issue_date=date.today(),
    )
    db_session.add(quotation)
    db_session.flush()

    package = QuotationPackageModel(quotation_id=quotation.quotation_id, name="Gói 1", sequence=1)
    db_session.add(package)
    db_session.flush()

    item = WorkItemModel(
        package_id=package.package_id,
        sequence=1,
        name="Sơn lót tường",
        description=None,
        quantity=Decimal("5"),
        unit="m2",
        unit_price=Decimal("100000"),
        total_price=Decimal("500000"),
        currency="VND",
    )
    db_session.add(item)
    db_session.commit()

    return {"project_id": project.project_id, "quotation_id": quotation.quotation_id, "item_id": item.item_id}


def test_search_work_items_returns_matches(db_session):
    ids = _seed(db_session)
    service = KnowledgeService()

    result = service.search_work_items(text="Sơn lót")

    assert any(r["item_id"] == ids["item_id"] for r in result["items"])
    assert result["matched_count"] == len(result["items"])


def test_search_work_items_matched_count_reflects_true_total_when_limited(db_session):
    project = ProjectModel(name="Nhà anh Tư", address="Q9")
    db_session.add(project)
    db_session.flush()
    quotation = QuotationModel(quotation_code="Q-101", project_id=project.project_id, currency="VND")
    db_session.add(quotation)
    db_session.flush()
    package = QuotationPackageModel(quotation_id=quotation.quotation_id, name="Gói 1", sequence=1)
    db_session.add(package)
    db_session.flush()
    for i in range(3):
        db_session.add(WorkItemModel(
            package_id=package.package_id, sequence=i + 1, name=f"Sơn lót tường {i}",
            unit="m2", unit_price=Decimal("100000"), currency="VND",
        ))
    db_session.commit()

    service = KnowledgeService()
    result = service.search_work_items(text="Sơn lót tường", limit=2)

    assert len(result["items"]) == 2
    assert result["matched_count"] == 3


def test_summarize_quotation_returns_totals(db_session):
    ids = _seed(db_session)
    service = KnowledgeService()

    result = service.summarize_quotation(ids["quotation_id"])

    assert result["num_work_items"] == 1
    assert result["total_amount"] == 500_000


def test_summarize_project_returns_totals(db_session):
    ids = _seed(db_session)
    service = KnowledgeService()

    result = service.summarize_project(ids["project_id"])

    assert result["num_work_items"] == 1


def test_compare_work_item_price_returns_none_for_missing_item(db_session):
    service = KnowledgeService()
    assert service.compare_work_item_price(999999) is None


def test_compare_work_item_price_returns_analysis_dict(db_session):
    ids = _seed(db_session)
    service = KnowledgeService()

    result = service.compare_work_item_price(ids["item_id"])

    assert result is not None
    assert "matched_count" in result


def test_compare_work_item_price_includes_matched_items_with_project_name(db_session):
    project = ProjectModel(name="Nhà anh Ba", address="Q3")
    db_session.add(project)
    db_session.flush()

    quotation = QuotationModel(quotation_code="Q-200", project_id=project.project_id, currency="VND")
    db_session.add(quotation)
    db_session.flush()

    package = QuotationPackageModel(quotation_id=quotation.quotation_id, name="Gói 1", sequence=1)
    db_session.add(package)
    db_session.flush()

    concept = ConceptModel(type="category", name="Sơn trang trí")
    db_session.add(concept)
    db_session.flush()

    historical = WorkItemModel(
        package_id=package.package_id, sequence=1, name="Sơn lót tường",
        description=None, quantity=Decimal("5"), unit="m2", unit_price=Decimal("40000"),
        total_price=Decimal("200000"), currency="VND", concepts=[concept],
    )
    db_session.add(historical)
    target = WorkItemModel(
        package_id=package.package_id, sequence=2, name="Sơn lót tường",
        description=None, quantity=Decimal("5"), unit="m2", unit_price=Decimal("42000"),
        total_price=Decimal("210000"), currency="VND", concepts=[concept],
    )
    db_session.add(target)
    db_session.commit()

    service = KnowledgeService()
    result = service.compare_work_item_price(target.item_id)

    assert result["matched_items"] == [
        {
            "item_id": historical.item_id,
            "name": "Sơn lót tường",
            "project_name": "Nhà anh Ba",
            "unit_price": Decimal("40000"),
            "name_similarity_score": 1.0,
        },
    ]


def test_get_estimation_returns_none_when_missing():
    service = KnowledgeService()
    assert service.get_estimation(999999) is None


def test_get_estimation_returns_data_when_present(db_session):
    project = ProjectModel(name="Villa Test", address="123 Test St")
    db_session.add(project)
    db_session.flush()
    db_session.add(EstimationModel(project_id=project.project_id, total_price=Decimal("1000000")))
    db_session.commit()

    service = KnowledgeService()
    result = service.get_estimation(project.project_id)

    assert result is not None
    assert result.total_price == Decimal("1000000")


def test_compare_project_labor_cost_returns_none_for_missing_project(db_session):
    service = KnowledgeService()
    assert service.compare_project_labor_cost(999999) is None


def test_compare_project_labor_cost_returns_comparison_dict(db_session):
    target = ProjectModel(name="Công trình đích", address="Q1")
    db_session.add(target)
    db_session.flush()
    target_estimation = EstimationModel(project_id=target.project_id)
    db_session.add(target_estimation)
    db_session.flush()
    target_quotation = QuotationModel(quotation_code="Q-T1", project_id=target.project_id)
    db_session.add(target_quotation)
    db_session.flush()
    target_package = QuotationPackageModel(quotation_id=target_quotation.quotation_id, name="Gói I", sequence=1)
    db_session.add(target_package)
    db_session.flush()
    concept = ConceptModel(type="category", name="Sơn nước")
    db_session.add(concept)
    db_session.flush()
    target_item = WorkItemModel(
        package_id=target_package.package_id, sequence=1, name="Hạng mục 1",
        currency="VND", concepts=[concept],
    )
    db_session.add(target_item)
    db_session.flush()
    target_cost_item = EstimationWorkItemModel(
        estimation_id=target_estimation.estimation_id, item_id=target_item.item_id, name="Hạng mục 1",
    )
    db_session.add(target_cost_item)
    db_session.flush()
    db_session.add(LaborInfoModel(
        cost_item_id=target_cost_item.cost_item_id, area=Decimal("100"),
        main_out_manday=Decimal("5"), main_out_total_price=Decimal("1000000"),
    ))

    other = ProjectModel(name="Công trình khác", address="Q2")
    db_session.add(other)
    db_session.flush()
    other_estimation = EstimationModel(project_id=other.project_id)
    db_session.add(other_estimation)
    db_session.flush()
    other_quotation = QuotationModel(quotation_code="Q-O1", project_id=other.project_id)
    db_session.add(other_quotation)
    db_session.flush()
    other_package = QuotationPackageModel(quotation_id=other_quotation.quotation_id, name="Gói I", sequence=1)
    db_session.add(other_package)
    db_session.flush()
    other_item = WorkItemModel(
        package_id=other_package.package_id, sequence=1, name="Hạng mục 1",
        currency="VND", concepts=[concept],
    )
    db_session.add(other_item)
    db_session.flush()
    other_cost_item = EstimationWorkItemModel(
        estimation_id=other_estimation.estimation_id, item_id=other_item.item_id, name="Hạng mục 1",
    )
    db_session.add(other_cost_item)
    db_session.flush()
    db_session.add(LaborInfoModel(
        cost_item_id=other_cost_item.cost_item_id, area=Decimal("100"),
        main_out_manday=Decimal("5"), main_out_total_price=Decimal("1500000"),
    ))
    db_session.commit()

    service = KnowledgeService()
    result = service.compare_project_labor_cost(target.project_id)

    assert result["project_id"] == target.project_id
    assert result["project_name"] == "Công trình đích"
    assert result["total_out_cost"] == Decimal("1000000")
    assert result["matched_count"] == 1
    assert result["matched_projects"] == [
        {
            "project_id": other.project_id,
            "name": "Công trình khác",
            "total_out_cost": Decimal("1500000"),
            "total_area": Decimal("100"),
            "cost_diff": Decimal("500000"),
            "cost_diff_pct": Decimal("50.00"),
            "similarity_score": 1.0,
        }
    ]


def test_compare_work_item_detail_returns_price_and_material_diff(db_session):
    project_a = ProjectModel(name="Công trình đích", address="Q1")
    db_session.add(project_a)
    db_session.flush()
    quotation_a = QuotationModel(quotation_code="Q-EDA", project_id=project_a.project_id)
    db_session.add(quotation_a)
    db_session.flush()
    package_a = QuotationPackageModel(quotation_id=quotation_a.quotation_id, name="Gói I", sequence=1)
    db_session.add(package_a)
    db_session.flush()
    item_a = WorkItemModel(
        package_id=package_a.package_id, sequence=1, name="Hạng mục A",
        unit="m2", unit_price=Decimal("100000"), currency="VND",
    )
    db_session.add(item_a)
    db_session.flush()
    estimation_a = EstimationModel(project_id=project_a.project_id)
    db_session.add(estimation_a)
    db_session.flush()
    cost_item_a = EstimationWorkItemModel(
        estimation_id=estimation_a.estimation_id, item_id=item_a.item_id, name="Hạng mục A",
        material_unit_price=Decimal("50000"), labor_unit_price=Decimal("30000"), profit_margin=Decimal("0.2"),
    )
    db_session.add(cost_item_a)
    db_session.flush()

    project_b = ProjectModel(name="Công trình khác", address="Q2")
    db_session.add(project_b)
    db_session.flush()
    quotation_b = QuotationModel(quotation_code="Q-EDB", project_id=project_b.project_id)
    db_session.add(quotation_b)
    db_session.flush()
    package_b = QuotationPackageModel(quotation_id=quotation_b.quotation_id, name="Gói I", sequence=1)
    db_session.add(package_b)
    db_session.flush()
    item_b = WorkItemModel(
        package_id=package_b.package_id, sequence=1, name="Hạng mục B",
        unit="m2", unit_price=Decimal("120000"), currency="VND",
    )
    db_session.add(item_b)
    db_session.flush()
    estimation_b = EstimationModel(project_id=project_b.project_id)
    db_session.add(estimation_b)
    db_session.flush()
    cost_item_b = EstimationWorkItemModel(
        estimation_id=estimation_b.estimation_id, item_id=item_b.item_id, name="Hạng mục B",
        material_unit_price=Decimal("60000"), labor_unit_price=Decimal("35000"), profit_margin=Decimal("0.25"),
    )
    db_session.add(cost_item_b)
    db_session.commit()

    service = KnowledgeService()
    result = service.compare_work_item_detail(item_a.item_id, item_b.item_id)

    assert result["item_id_a"] == item_a.item_id
    assert result["item_id_b"] == item_b.item_id
    assert result["unit_price_a"] == Decimal("100000")
    assert result["unit_price_b"] == Decimal("120000")
    assert result["price_diff"] == Decimal("20000")
    assert result["price_diff_pct"] == Decimal("20.00")
    assert result["material_unit_price_diff"] == Decimal("10000")
    assert result["labor_unit_price_diff"] == Decimal("5000")
    assert result["profit_margin_diff"] == Decimal("0.05")
    assert result["labor_info_diff"] is None
    assert result["materials"] == []
    assert result["processes"] == []


def test_compare_work_item_detail_returns_none_for_missing_item(db_session):
    service = KnowledgeService()
    assert service.compare_work_item_detail(999999, 999998) is None


def test_compare_project_cost_breakdown_returns_none_for_missing_project(db_session):
    service = KnowledgeService()
    assert service.compare_project_cost_breakdown(999999, "material") is None


def test_compare_project_cost_breakdown_returns_comparison_dict(db_session):
    target = ProjectModel(name="Công trình đích", address="Q1")
    db_session.add(target)
    db_session.flush()
    target_quotation = QuotationModel(quotation_code="Q-CB1", project_id=target.project_id, total_amount=Decimal("1000000"))
    db_session.add(target_quotation)
    db_session.flush()
    target_estimation = EstimationModel(project_id=target.project_id)
    db_session.add(target_estimation)
    db_session.flush()
    db_session.add(TotalDetailModel(
        estimation_id=target_estimation.estimation_id, type="nhân công", name="nhân công", price=Decimal("300000"),
    ))

    other = ProjectModel(name="Công trình khác", address="Q2")
    db_session.add(other)
    db_session.flush()
    other_quotation = QuotationModel(quotation_code="Q-CB2", project_id=other.project_id, total_amount=Decimal("1000000"))
    db_session.add(other_quotation)
    db_session.flush()
    other_estimation = EstimationModel(project_id=other.project_id)
    db_session.add(other_estimation)
    db_session.flush()
    db_session.add(TotalDetailModel(
        estimation_id=other_estimation.estimation_id, type="nhân công", name="nhân công", price=Decimal("500000"),
    ))
    db_session.commit()

    service = KnowledgeService()
    result = service.compare_project_cost_breakdown(target.project_id, "labor")

    assert result["project_id"] == target.project_id
    assert result["cost_type"] == "labor"
    assert result["price"] == Decimal("300000")
    assert result["pct_of_total"] == Decimal("30.00")
    assert result["matched_count"] == 1
    assert result["matched_projects"] == [
        {
            "project_id": other.project_id,
            "name": "Công trình khác",
            "price": Decimal("500000"),
            "pct_of_total": Decimal("50.00"),
        }
    ]
