from decimal import Decimal

from app.domains.quotation.infrastructure.persistence.models import (
    EstimationModel, EstimationWorkItemModel, LaborInfoModel, LaborInfoProcessModel,
    MainMaterialModel, ProjectModel, QuotationModel, QuotationPackageModel, WorkItemModel,
)
from app.domains.quotation.application.services.estimation_service import (
    EstimationApplicationService,
)
from app.domains.quotation.infrastructure.persistence.repositories.estimation_repository import (
    SqlAlchemyEstimationRepository,
)


def _seed_work_item_only(db_session, suffix, unit_price):
    project = ProjectModel(name=f"Công trình {suffix}", address="Q1")
    db_session.add(project)
    db_session.flush()
    quotation = QuotationModel(quotation_code=f"Q-{suffix}", project_id=project.project_id)
    db_session.add(quotation)
    db_session.flush()
    package = QuotationPackageModel(quotation_id=quotation.quotation_id, name="Gói I", sequence=1)
    db_session.add(package)
    db_session.flush()
    work_item = WorkItemModel(
        package_id=package.package_id, sequence=1, name=f"Hạng mục {suffix}",
        unit="m2", unit_price=unit_price, currency="VND",
    )
    db_session.add(work_item)
    db_session.commit()
    return work_item


def _seed_hang_muc(db_session, suffix, unit_price, material_unit_price, labor_unit_price, profit_margin,
                    materials=None, labor_info_kwargs=None, processes=None):
    project = ProjectModel(name=f"Công trình {suffix}", address="Q1")
    db_session.add(project)
    db_session.flush()
    quotation = QuotationModel(quotation_code=f"Q-{suffix}", project_id=project.project_id)
    db_session.add(quotation)
    db_session.flush()
    package = QuotationPackageModel(quotation_id=quotation.quotation_id, name="Gói I", sequence=1)
    db_session.add(package)
    db_session.flush()
    work_item = WorkItemModel(
        package_id=package.package_id, sequence=1, name=f"Hạng mục {suffix}",
        unit="m2", unit_price=unit_price, currency="VND",
    )
    db_session.add(work_item)
    db_session.flush()

    estimation = EstimationModel(project_id=project.project_id)
    db_session.add(estimation)
    db_session.flush()

    cost_item = EstimationWorkItemModel(
        estimation_id=estimation.estimation_id, item_id=work_item.item_id, name=f"Hạng mục {suffix}",
        material_unit_price=material_unit_price, labor_unit_price=labor_unit_price, profit_margin=profit_margin,
    )
    db_session.add(cost_item)
    db_session.flush()

    if labor_info_kwargs is not None:
        labor_info = LaborInfoModel(cost_item_id=cost_item.cost_item_id, **labor_info_kwargs)
        db_session.add(labor_info)
        db_session.flush()
        for process_kwargs in (processes or []):
            db_session.add(LaborInfoProcessModel(labor_id=labor_info.labor_id, **process_kwargs))

    for material_kwargs in (materials or []):
        db_session.add(MainMaterialModel(cost_item_id=cost_item.cost_item_id, **material_kwargs))

    db_session.commit()
    return work_item


def test_compare_returns_none_when_either_item_not_found(db_session):
    item_a = _seed_hang_muc(db_session, "A", unit_price=Decimal("100000"),
                             material_unit_price=Decimal("50000"), labor_unit_price=Decimal("30000"),
                             profit_margin=Decimal("0.2"))

    comparator = EstimationApplicationService(SqlAlchemyEstimationRepository(db_session), db_session)
    assert comparator.compare_detail(item_a.item_id, 999999) is None
    assert comparator.compare_detail(999999, item_a.item_id) is None


def test_compare_returns_none_when_either_item_has_no_estimation(db_session):
    item_a = _seed_hang_muc(db_session, "A", unit_price=Decimal("100000"),
                             material_unit_price=Decimal("50000"), labor_unit_price=Decimal("30000"),
                             profit_margin=Decimal("0.2"))
    item_b = _seed_work_item_only(db_session, "B", unit_price=Decimal("110000"))

    comparator = EstimationApplicationService(SqlAlchemyEstimationRepository(db_session), db_session)
    assert comparator.compare_detail(item_a.item_id, item_b.item_id) is None


def test_price_attribution_diffs_computed_correctly(db_session):
    item_a = _seed_hang_muc(db_session, "A", unit_price=Decimal("100000"),
                             material_unit_price=Decimal("50000"), labor_unit_price=Decimal("30000"),
                             profit_margin=Decimal("0.2"))
    item_b = _seed_hang_muc(db_session, "B", unit_price=Decimal("120000"),
                             material_unit_price=Decimal("60000"), labor_unit_price=Decimal("35000"),
                             profit_margin=Decimal("0.25"))

    comparator = EstimationApplicationService(SqlAlchemyEstimationRepository(db_session), db_session)
    diff = comparator.compare_detail(item_a.item_id, item_b.item_id)

    assert diff.unit_price_a == Decimal("100000")
    assert diff.unit_price_b == Decimal("120000")
    assert diff.price_diff == Decimal("20000")
    assert diff.price_diff_pct == Decimal("20.00")
    assert diff.material_unit_price_diff == Decimal("10000")
    assert diff.labor_unit_price_diff == Decimal("5000")
    assert diff.profit_margin_diff == Decimal("0.05")


def test_materials_matched_and_split_by_similarity(db_session):
    item_a = _seed_hang_muc(
        db_session, "A", unit_price=Decimal("100000"),
        material_unit_price=Decimal("50000"), labor_unit_price=Decimal("30000"), profit_margin=Decimal("0.2"),
        materials=[
            {"product_name": "Vietcoat Seal-11A Plus", "layers": 2, "construction_loss": Decimal("0.05"),
             "theoretical_rate": Decimal("10"), "unit_price_per_m2": Decimal("20000"),
             "total_price_area_based": Decimal("2000000")},
            {"product_name": "Bột trét tường ngoài", "layers": 1, "construction_loss": Decimal("0.03"),
             "theoretical_rate": Decimal("5"), "unit_price_per_m2": Decimal("8000"),
             "total_price_area_based": Decimal("800000")},
        ],
    )
    item_b = _seed_hang_muc(
        db_session, "B", unit_price=Decimal("110000"),
        material_unit_price=Decimal("55000"), labor_unit_price=Decimal("30000"), profit_margin=Decimal("0.2"),
        materials=[
            {"product_name": "Vietcoat Seal-11A Plus", "layers": 3, "construction_loss": Decimal("0.06"),
             "theoretical_rate": Decimal("10"), "unit_price_per_m2": Decimal("28000"),
             "total_price_area_based": Decimal("2800000")},
            {"product_name": "Sơn lót chống kiềm", "layers": 1, "construction_loss": Decimal("0.02"),
             "theoretical_rate": Decimal("6"), "unit_price_per_m2": Decimal("9000"),
             "total_price_area_based": Decimal("900000")},
        ],
    )

    comparator = EstimationApplicationService(SqlAlchemyEstimationRepository(db_session), db_session)
    diff = comparator.compare_detail(item_a.item_id, item_b.item_id)

    assert len(diff.materials) == 3
    matched = [m for m in diff.materials if m.match_type == "matched"]
    only_a = [m for m in diff.materials if m.match_type == "only_a"]
    only_b = [m for m in diff.materials if m.match_type == "only_b"]
    assert len(matched) == 1
    assert matched[0].a.product_name == "Vietcoat Seal-11A Plus"
    assert matched[0].b.product_name == "Vietcoat Seal-11A Plus"
    assert matched[0].name_similarity_score == 1.0
    assert matched[0].a.layers == 2
    assert matched[0].b.layers == 3
    assert matched[0].a.construction_loss == Decimal("0.05")
    assert matched[0].b.construction_loss == Decimal("0.06")
    assert len(only_a) == 1
    assert only_a[0].a.product_name == "Bột trét tường ngoài"
    assert only_a[0].b is None
    assert only_a[0].name_similarity_score is None
    assert len(only_b) == 1
    assert only_b[0].b.product_name == "Sơn lót chống kiềm"
    assert only_b[0].a is None
    assert only_b[0].name_similarity_score is None


def test_materials_matched_when_similar_but_not_exact(db_session):
    item_a = _seed_hang_muc(
        db_session, "A", unit_price=Decimal("100000"),
        material_unit_price=Decimal("50000"), labor_unit_price=Decimal("30000"), profit_margin=Decimal("0.2"),
        materials=[
            {"product_name": "Sơn lót chống kiềm ngoài trời", "layers": 1,
             "theoretical_rate": Decimal("8"), "unit_price_per_m2": Decimal("9000")},
        ],
    )
    item_b = _seed_hang_muc(
        db_session, "B", unit_price=Decimal("105000"),
        material_unit_price=Decimal("52000"), labor_unit_price=Decimal("30000"), profit_margin=Decimal("0.2"),
        materials=[
            {"product_name": "Sơn lót chống kiềm nội thất", "layers": 1,
             "theoretical_rate": Decimal("8"), "unit_price_per_m2": Decimal("9500")},
        ],
    )

    comparator = EstimationApplicationService(SqlAlchemyEstimationRepository(db_session), db_session)
    diff = comparator.compare_detail(item_a.item_id, item_b.item_id)

    assert len(diff.materials) == 1
    assert diff.materials[0].match_type == "matched"
    assert diff.materials[0].name_similarity_score == 0.8214
    assert diff.materials[0].a.product_name == "Sơn lót chống kiềm ngoài trời"
    assert diff.materials[0].b.product_name == "Sơn lót chống kiềm nội thất"
    assert diff.materials[0].a.unit_price_per_m2 == Decimal("9000")
    assert diff.materials[0].b.unit_price_per_m2 == Decimal("9500")


def test_processes_matched_and_split_same_as_materials(db_session):
    item_a = _seed_hang_muc(
        db_session, "A", unit_price=Decimal("100000"),
        material_unit_price=Decimal("50000"), labor_unit_price=Decimal("30000"), profit_margin=Decimal("0.2"),
        labor_info_kwargs={"area": Decimal("100")},
        processes=[
            {"name": "Thi công sơn lót", "main_labors_out": 2, "days": Decimal("3"), "main_out_manday": Decimal("6")},
            {"name": "Vệ sinh bề mặt", "main_labors_out": 1, "days": Decimal("1"), "main_out_manday": Decimal("1")},
        ],
    )
    item_b = _seed_hang_muc(
        db_session, "B", unit_price=Decimal("110000"),
        material_unit_price=Decimal("55000"), labor_unit_price=Decimal("30000"), profit_margin=Decimal("0.2"),
        labor_info_kwargs={"area": Decimal("100")},
        processes=[
            {"name": "Thi công sơn lót", "main_labors_out": 3, "days": Decimal("3"), "main_out_manday": Decimal("9")},
            {"name": "Lắp đặt giàn giáo", "main_labors_out": 2, "days": Decimal("1"), "main_out_manday": Decimal("2")},
        ],
    )

    comparator = EstimationApplicationService(SqlAlchemyEstimationRepository(db_session), db_session)
    diff = comparator.compare_detail(item_a.item_id, item_b.item_id)

    assert len(diff.processes) == 3
    matched = [p for p in diff.processes if p.match_type == "matched"]
    only_a = [p for p in diff.processes if p.match_type == "only_a"]
    only_b = [p for p in diff.processes if p.match_type == "only_b"]
    assert len(matched) == 1
    assert matched[0].a.name == "Thi công sơn lót"
    assert matched[0].b.name == "Thi công sơn lót"
    assert matched[0].name_similarity_score == 1.0
    assert matched[0].a.main_out_manday == Decimal("6")
    assert matched[0].b.main_out_manday == Decimal("9")
    assert len(only_a) == 1
    assert only_a[0].a.name == "Vệ sinh bề mặt"
    assert len(only_b) == 1
    assert only_b[0].b.name == "Lắp đặt giàn giáo"


def test_processes_matched_when_similar_but_not_exact(db_session):
    item_a = _seed_hang_muc(
        db_session, "A", unit_price=Decimal("100000"),
        material_unit_price=Decimal("50000"), labor_unit_price=Decimal("30000"), profit_margin=Decimal("0.2"),
        labor_info_kwargs={"area": Decimal("100")},
        processes=[
            {"name": "Trộn vữa tô tường", "main_labors_out": 2, "days": Decimal("2"), "main_out_manday": Decimal("4")},
        ],
    )
    item_b = _seed_hang_muc(
        db_session, "B", unit_price=Decimal("105000"),
        material_unit_price=Decimal("52000"), labor_unit_price=Decimal("30000"), profit_margin=Decimal("0.2"),
        labor_info_kwargs={"area": Decimal("100")},
        processes=[
            {"name": "Trộn vữa tô trần", "main_labors_out": 3, "days": Decimal("2"), "main_out_manday": Decimal("6")},
        ],
    )

    comparator = EstimationApplicationService(SqlAlchemyEstimationRepository(db_session), db_session)
    diff = comparator.compare_detail(item_a.item_id, item_b.item_id)

    assert len(diff.processes) == 1
    assert diff.processes[0].match_type == "matched"
    assert diff.processes[0].name_similarity_score == 0.8485
    assert diff.processes[0].a.name == "Trộn vữa tô tường"
    assert diff.processes[0].b.name == "Trộn vữa tô trần"
    assert diff.processes[0].a.main_out_manday == Decimal("4")
    assert diff.processes[0].b.main_out_manday == Decimal("6")


def test_labor_info_diff_is_none_when_either_side_missing_labor_info(db_session):
    item_a = _seed_hang_muc(
        db_session, "A", unit_price=Decimal("100000"),
        material_unit_price=Decimal("50000"), labor_unit_price=Decimal("30000"), profit_margin=Decimal("0.2"),
        labor_info_kwargs={"area": Decimal("100"), "labor_coeff": Decimal("1.05")},
    )
    item_b = _seed_hang_muc(
        db_session, "B", unit_price=Decimal("110000"),
        material_unit_price=Decimal("55000"), labor_unit_price=Decimal("30000"), profit_margin=Decimal("0.2"),
    )

    comparator = EstimationApplicationService(SqlAlchemyEstimationRepository(db_session), db_session)
    diff = comparator.compare_detail(item_a.item_id, item_b.item_id)

    assert diff.labor_info_diff is None
    # Materials/processes/top-level price fields are unaffected by the missing labor_info.
    assert diff.material_unit_price_diff == Decimal("5000")


def test_labor_info_diff_populated_when_both_sides_have_labor_info(db_session):
    item_a = _seed_hang_muc(
        db_session, "A", unit_price=Decimal("100000"),
        material_unit_price=Decimal("50000"), labor_unit_price=Decimal("30000"), profit_margin=Decimal("0.2"),
        labor_info_kwargs={
            "area": Decimal("100"), "final_unit_price_type": "has_kn", "labor_coeff": Decimal("1.05"),
            "kn_manday": Decimal("10"), "main_out_manday": Decimal("5"), "sub_out_manday": Decimal("2"),
        },
    )
    item_b = _seed_hang_muc(
        db_session, "B", unit_price=Decimal("110000"),
        material_unit_price=Decimal("55000"), labor_unit_price=Decimal("30000"), profit_margin=Decimal("0.2"),
        labor_info_kwargs={
            "area": Decimal("120"), "final_unit_price_type": "all_out", "labor_coeff": Decimal("1.10"),
            "kn_manday": Decimal("4"), "main_out_manday": Decimal("8"), "sub_out_manday": Decimal("3"),
        },
    )

    comparator = EstimationApplicationService(SqlAlchemyEstimationRepository(db_session), db_session)
    diff = comparator.compare_detail(item_a.item_id, item_b.item_id)

    assert diff.labor_info_diff is not None
    assert diff.labor_info_diff.final_unit_price_type_a == "has_kn"
    assert diff.labor_info_diff.final_unit_price_type_b == "all_out"
    assert diff.labor_info_diff.labor_coeff_diff == Decimal("0.05")
    assert diff.labor_info_diff.kn_manday_diff == Decimal("-6")
    assert diff.labor_info_diff.main_out_manday_diff == Decimal("3")
    assert diff.labor_info_diff.sub_out_manday_diff == Decimal("1")
    assert diff.labor_info_diff.area_diff == Decimal("20")


def test_none_safe_diffs_when_field_missing_on_one_side(db_session):
    item_a = _seed_hang_muc(
        db_session, "A", unit_price=Decimal("100000"),
        material_unit_price=Decimal("50000"), labor_unit_price=Decimal("30000"), profit_margin=Decimal("0.2"),
        labor_info_kwargs={"area": Decimal("100"), "labor_coeff": None},
    )
    item_b = _seed_hang_muc(
        db_session, "B", unit_price=Decimal("110000"),
        material_unit_price=Decimal("55000"), labor_unit_price=Decimal("30000"), profit_margin=Decimal("0.2"),
        labor_info_kwargs={"area": Decimal("120"), "labor_coeff": Decimal("1.10")},
    )

    comparator = EstimationApplicationService(SqlAlchemyEstimationRepository(db_session), db_session)
    diff = comparator.compare_detail(item_a.item_id, item_b.item_id)

    assert diff.labor_info_diff.labor_coeff_a is None
    assert diff.labor_info_diff.labor_coeff_b == Decimal("1.10")
    assert diff.labor_info_diff.labor_coeff_diff is None
