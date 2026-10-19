from decimal import Decimal

from app.domains.quotation.infrastructure.persistence.models import (
    ProjectModel, QuotationModel, QuotationPackageModel, WorkItemModel,
    EstimationModel, TotalDetailModel, EstimationWorkItemModel,
    LaborInfoModel, LaborInfoProcessModel, MainMaterialModel,
)
from app.domains.quotation.infrastructure.persistence.repositories.estimation_repository import (
    SqlAlchemyEstimationRepository,
)
from app.domains.quotation.application.dto import (
    CreateEstimationBundleData, CreateEstimationData, CreateTotalDetailData,
    CreateEstimationWorkItemData, CreateLaborInfoData, CreateLaborInfoProcessData,
    CreateMainMaterialData, CreateSubMaterialData, CreateItemSubData, CreateProductToBuyData,
)


def _seed_full_estimation(db_session):
    project = ProjectModel(name="Villa Test", address="123 Test St")
    db_session.add(project)
    db_session.flush()

    quotation = QuotationModel(quotation_code="Q-001", project_id=project.project_id)
    db_session.add(quotation)
    db_session.flush()
    package = QuotationPackageModel(quotation_id=quotation.quotation_id, name="Gói I", sequence=1)
    db_session.add(package)
    db_session.flush()
    work_item = WorkItemModel(package_id=package.package_id, sequence=1, name="Sơn tường", currency="VND")
    db_session.add(work_item)
    db_session.flush()

    estimation = EstimationModel(project_id=project.project_id, total_price=Decimal("285634855.25"))
    db_session.add(estimation)
    db_session.flush()
    db_session.add(TotalDetailModel(estimation_id=estimation.estimation_id, type="vật tư chính", name="vật tư chính", price=Decimal("157509773.87")))
    db_session.flush()

    cost_item = EstimationWorkItemModel(estimation_id=estimation.estimation_id, item_id=work_item.item_id, name="Hạng mục 1", labor_unit_price=Decimal("181980.37"))
    db_session.add(cost_item)
    db_session.flush()

    labor = LaborInfoModel(cost_item_id=cost_item.cost_item_id, final_unit_price_type="has_kn", labor_unit_price=Decimal("181980.37"))
    db_session.add(labor)
    db_session.flush()
    db_session.add(LaborInfoProcessModel(labor_id=labor.labor_id, name="Chống thấm 2 lớp"))
    db_session.add(MainMaterialModel(cost_item_id=cost_item.cost_item_id, product_name="VIETCOAT SEAL-11A PLUS SÀN"))
    db_session.commit()

    return project, work_item


def test_get_by_project_id_returns_estimation_with_total_details(db_session):
    project, _ = _seed_full_estimation(db_session)
    repo = SqlAlchemyEstimationRepository(db_session)

    estimation = repo.get_by_project_id(project.project_id)

    assert estimation is not None
    assert estimation.total_price == Decimal("285634855.25")
    assert len(estimation.total_details) == 1
    assert estimation.total_details[0].type == "vật tư chính"


def test_get_by_project_id_returns_none_when_missing(db_session):
    repo = SqlAlchemyEstimationRepository(db_session)
    assert repo.get_by_project_id(999999) is None


def test_get_by_project_id_returns_labor_summary_aggregated_across_items(db_session):
    project = ProjectModel(name="Villa Manday", address="456 Test St")
    db_session.add(project)
    db_session.flush()

    quotation = QuotationModel(quotation_code="Q-002", project_id=project.project_id)
    db_session.add(quotation)
    db_session.flush()
    package = QuotationPackageModel(quotation_id=quotation.quotation_id, name="Gói I", sequence=1)
    db_session.add(package)
    db_session.flush()

    estimation = EstimationModel(project_id=project.project_id, total_price=Decimal("100000000"))
    db_session.add(estimation)
    db_session.flush()

    item_1 = WorkItemModel(package_id=package.package_id, sequence=1, name="Hạng mục 1", currency="VND")
    item_2 = WorkItemModel(package_id=package.package_id, sequence=2, name="Hạng mục 2", currency="VND")
    item_3 = WorkItemModel(package_id=package.package_id, sequence=3, name="Hạng mục 3", currency="VND")
    db_session.add_all([item_1, item_2, item_3])
    db_session.flush()

    cost_item_1 = EstimationWorkItemModel(estimation_id=estimation.estimation_id, item_id=item_1.item_id, name="Hạng mục 1")
    cost_item_2 = EstimationWorkItemModel(estimation_id=estimation.estimation_id, item_id=item_2.item_id, name="Hạng mục 2")
    cost_item_3 = EstimationWorkItemModel(estimation_id=estimation.estimation_id, item_id=item_3.item_id, name="Hạng mục 3 (không có labor_info)")
    db_session.add_all([cost_item_1, cost_item_2, cost_item_3])
    db_session.flush()

    db_session.add(LaborInfoModel(
        cost_item_id=cost_item_1.cost_item_id,
        kn_manday=Decimal("10"), main_out_manday=Decimal("5"), sub_out_manday=Decimal("2"),
    ))
    db_session.add(LaborInfoModel(
        cost_item_id=cost_item_2.cost_item_id,
        kn_manday=Decimal("3"), main_out_manday=None, sub_out_manday=Decimal("1"),
    ))
    # cost_item_3 deliberately has no LaborInfo row at all.
    db_session.commit()

    repo = SqlAlchemyEstimationRepository(db_session)
    estimation_data = repo.get_by_project_id(project.project_id)

    assert estimation_data is not None
    assert estimation_data.labor_summary.total_kn_manday == Decimal("13")
    assert estimation_data.labor_summary.total_main_out_manday == Decimal("5")
    assert estimation_data.labor_summary.total_sub_out_manday == Decimal("3")
    assert estimation_data.labor_summary.total_out_manday == Decimal("8")
    assert estimation_data.labor_summary.total_manday == Decimal("21")


def test_get_by_project_id_labor_summary_is_zero_when_no_manday_data(db_session):
    project, _ = _seed_full_estimation(db_session)
    repo = SqlAlchemyEstimationRepository(db_session)

    estimation_data = repo.get_by_project_id(project.project_id)

    assert estimation_data.labor_summary.total_kn_manday == Decimal("0")
    assert estimation_data.labor_summary.total_main_out_manday == Decimal("0")
    assert estimation_data.labor_summary.total_sub_out_manday == Decimal("0")
    assert estimation_data.labor_summary.total_out_manday == Decimal("0")
    assert estimation_data.labor_summary.total_manday == Decimal("0")


def test_get_work_item_detail_nests_labor_and_material(db_session):
    _, work_item = _seed_full_estimation(db_session)
    repo = SqlAlchemyEstimationRepository(db_session)

    detail = repo.get_work_item_detail(work_item.item_id)

    assert detail is not None
    assert detail.labor_info is not None
    assert detail.labor_info.processes[0].name == "Chống thấm 2 lớp"
    assert detail.main_materials[0].product_name == "VIETCOAT SEAL-11A PLUS SÀN"


def test_get_work_item_detail_returns_none_when_no_estimation_row(db_session):
    repo = SqlAlchemyEstimationRepository(db_session)
    assert repo.get_work_item_detail(999999) is None


def test_get_work_item_detail_computes_main_and_sub_out_unit_price(db_session):
    project = ProjectModel(name="Villa Unit Price", address="789 Test St")
    db_session.add(project)
    db_session.flush()
    quotation = QuotationModel(quotation_code="Q-003", project_id=project.project_id)
    db_session.add(quotation)
    db_session.flush()
    package = QuotationPackageModel(quotation_id=quotation.quotation_id, name="Gói I", sequence=1)
    db_session.add(package)
    db_session.flush()
    work_item = WorkItemModel(package_id=package.package_id, sequence=1, name="Sơn tường", currency="VND")
    db_session.add(work_item)
    db_session.flush()
    estimation = EstimationModel(project_id=project.project_id)
    db_session.add(estimation)
    db_session.flush()
    cost_item = EstimationWorkItemModel(estimation_id=estimation.estimation_id, item_id=work_item.item_id, name="Hạng mục 1")
    db_session.add(cost_item)
    db_session.flush()
    db_session.add(LaborInfoModel(
        cost_item_id=cost_item.cost_item_id,
        main_out_manday=Decimal("5"), main_out_total_price=Decimal("1500000"),
        sub_out_manday=Decimal("2"), sub_out_total_price=Decimal("400000"),
    ))
    db_session.commit()

    repo = SqlAlchemyEstimationRepository(db_session)
    detail = repo.get_work_item_detail(work_item.item_id)

    assert detail.labor_info.main_out_unit_price == Decimal("300000.00")
    assert detail.labor_info.sub_out_unit_price == Decimal("200000.00")


def test_get_work_item_detail_hired_labor_unit_price_is_none_when_manday_missing(db_session):
    _, work_item = _seed_full_estimation(db_session)
    repo = SqlAlchemyEstimationRepository(db_session)

    detail = repo.get_work_item_detail(work_item.item_id)

    assert detail.labor_info.main_out_unit_price is None
    assert detail.labor_info.sub_out_unit_price is None


def test_get_work_item_detail_hired_labor_unit_price_is_none_when_total_price_missing(db_session):
    project = ProjectModel(name="Villa Missing Price", address="111 Test St")
    db_session.add(project)
    db_session.flush()
    quotation = QuotationModel(quotation_code="Q-005", project_id=project.project_id)
    db_session.add(quotation)
    db_session.flush()
    package = QuotationPackageModel(quotation_id=quotation.quotation_id, name="Gói I", sequence=1)
    db_session.add(package)
    db_session.flush()
    work_item = WorkItemModel(package_id=package.package_id, sequence=1, name="Sơn tường", currency="VND")
    db_session.add(work_item)
    db_session.flush()
    estimation = EstimationModel(project_id=project.project_id)
    db_session.add(estimation)
    db_session.flush()
    cost_item = EstimationWorkItemModel(estimation_id=estimation.estimation_id, item_id=work_item.item_id, name="Hạng mục 1")
    db_session.add(cost_item)
    db_session.flush()
    db_session.add(LaborInfoModel(
        cost_item_id=cost_item.cost_item_id,
        main_out_manday=Decimal("5"), main_out_total_price=None,
        sub_out_manday=Decimal("2"), sub_out_total_price=None,
    ))
    db_session.commit()

    repo = SqlAlchemyEstimationRepository(db_session)
    detail = repo.get_work_item_detail(work_item.item_id)

    assert detail.labor_info.main_out_unit_price is None
    assert detail.labor_info.sub_out_unit_price is None


def test_get_work_item_detail_hired_labor_unit_price_is_none_when_manday_is_zero(db_session):
    project = ProjectModel(name="Villa Zero Manday", address="000 Test St")
    db_session.add(project)
    db_session.flush()
    quotation = QuotationModel(quotation_code="Q-004", project_id=project.project_id)
    db_session.add(quotation)
    db_session.flush()
    package = QuotationPackageModel(quotation_id=quotation.quotation_id, name="Gói I", sequence=1)
    db_session.add(package)
    db_session.flush()
    work_item = WorkItemModel(package_id=package.package_id, sequence=1, name="Sơn tường", currency="VND")
    db_session.add(work_item)
    db_session.flush()
    estimation = EstimationModel(project_id=project.project_id)
    db_session.add(estimation)
    db_session.flush()
    cost_item = EstimationWorkItemModel(estimation_id=estimation.estimation_id, item_id=work_item.item_id, name="Hạng mục 1")
    db_session.add(cost_item)
    db_session.flush()
    db_session.add(LaborInfoModel(
        cost_item_id=cost_item.cost_item_id,
        main_out_manday=Decimal("0"), main_out_total_price=Decimal("0"),
        sub_out_manday=Decimal("0"), sub_out_total_price=Decimal("0"),
    ))
    db_session.commit()

    repo = SqlAlchemyEstimationRepository(db_session)
    detail = repo.get_work_item_detail(work_item.item_id)

    assert detail.labor_info.main_out_unit_price is None
    assert detail.labor_info.sub_out_unit_price is None


def test_get_by_project_id_computes_cost_breakdown_by_type(db_session):
    project = ProjectModel(name="Villa Breakdown", address="789 Test St")
    db_session.add(project)
    db_session.flush()
    quotation = QuotationModel(quotation_code="Q-003", project_id=project.project_id, total_amount=Decimal("1000000"))
    db_session.add(quotation)
    db_session.flush()
    package = QuotationPackageModel(quotation_id=quotation.quotation_id, name="Gói I", sequence=1)
    db_session.add(package)
    db_session.flush()

    estimation = EstimationModel(project_id=project.project_id)
    db_session.add(estimation)
    db_session.flush()
    db_session.add(TotalDetailModel(estimation_id=estimation.estimation_id, type="vật tư chính", name="vật tư chính", price=Decimal("400000")))
    db_session.add(TotalDetailModel(estimation_id=estimation.estimation_id, type="vật tư phụ", name="vật tư phụ", price=Decimal("100000")))
    db_session.add(TotalDetailModel(estimation_id=estimation.estimation_id, type="nhân công", name="nhân công", price=Decimal("300000")))
    db_session.add(TotalDetailModel(estimation_id=estimation.estimation_id, type="chi phí khác", name="chi phí khác", price=Decimal("200000")))
    db_session.commit()

    repo = SqlAlchemyEstimationRepository(db_session)
    estimation_data = repo.get_by_project_id(project.project_id)

    assert estimation_data.cost_breakdown.quotation_total_amount == Decimal("1000000")
    by_type = {item.type: item for item in estimation_data.cost_breakdown.by_type}
    assert by_type["vật tư chính"].price == Decimal("400000")
    assert by_type["vật tư chính"].pct_of_quotation_total == Decimal("40.00")
    assert by_type["vật tư phụ"].pct_of_quotation_total == Decimal("10.00")
    assert by_type["nhân công"].pct_of_quotation_total == Decimal("30.00")
    assert by_type["chi phí khác"].pct_of_quotation_total == Decimal("20.00")
    assert estimation_data.cost_breakdown.material_total == Decimal("500000")
    assert estimation_data.cost_breakdown.material_pct == Decimal("50.00")
    assert estimation_data.cost_breakdown.labor_total == Decimal("300000")
    assert estimation_data.cost_breakdown.labor_pct == Decimal("30.00")


def test_get_by_project_id_cost_breakdown_normalizes_type_casing(db_session):
    project = ProjectModel(name="Villa Casing", address="1 Test St")
    db_session.add(project)
    db_session.flush()
    quotation = QuotationModel(quotation_code="Q-004", project_id=project.project_id, total_amount=Decimal("100000"))
    db_session.add(quotation)
    db_session.flush()
    package = QuotationPackageModel(quotation_id=quotation.quotation_id, name="Gói I", sequence=1)
    db_session.add(package)
    db_session.flush()
    estimation = EstimationModel(project_id=project.project_id)
    db_session.add(estimation)
    db_session.flush()
    db_session.add(TotalDetailModel(estimation_id=estimation.estimation_id, type="Vật Tư Chính ", name="vật tư chính", price=Decimal("60000")))
    db_session.add(TotalDetailModel(estimation_id=estimation.estimation_id, type=" NHÂN CÔNG", name="nhân công", price=Decimal("40000")))
    db_session.commit()

    repo = SqlAlchemyEstimationRepository(db_session)
    estimation_data = repo.get_by_project_id(project.project_id)

    assert estimation_data.cost_breakdown.material_total == Decimal("60000")
    assert estimation_data.cost_breakdown.labor_total == Decimal("40000")


def test_get_by_project_id_cost_breakdown_pct_is_none_when_quotation_total_is_zero(db_session):
    project, _ = _seed_full_estimation(db_session)
    repo = SqlAlchemyEstimationRepository(db_session)

    estimation_data = repo.get_by_project_id(project.project_id)

    assert estimation_data.cost_breakdown.quotation_total_amount == Decimal("0")
    assert estimation_data.cost_breakdown.by_type[0].pct_of_quotation_total is None
    assert estimation_data.cost_breakdown.material_pct is None
    assert estimation_data.cost_breakdown.labor_pct is None


def test_get_by_project_id_cost_breakdown_is_empty_when_no_total_details(db_session):
    project = ProjectModel(name="Villa Empty", address="2 Test St")
    db_session.add(project)
    db_session.flush()
    quotation = QuotationModel(quotation_code="Q-005", project_id=project.project_id, total_amount=Decimal("500000"))
    db_session.add(quotation)
    db_session.flush()
    package = QuotationPackageModel(quotation_id=quotation.quotation_id, name="Gói I", sequence=1)
    db_session.add(package)
    db_session.flush()
    estimation = EstimationModel(project_id=project.project_id)
    db_session.add(estimation)
    db_session.commit()

    repo = SqlAlchemyEstimationRepository(db_session)
    estimation_data = repo.get_by_project_id(project.project_id)

    assert estimation_data.cost_breakdown.by_type == []
    assert estimation_data.cost_breakdown.material_total == Decimal("0")
    assert estimation_data.cost_breakdown.labor_total == Decimal("0")


def test_create_writes_all_nine_tables_and_get_by_project_id_reads_it_back(db_session):
    # Same "create a ProjectModel row inline, no shared fixture" pattern every
    # other test in this file already uses (see e.g. test_get_by_project_id_
    # returns_estimation_with_total_details above).
    project = ProjectModel(name="Villa Create Test", address="1 Test St")
    db_session.add(project)
    db_session.flush()

    bundle = CreateEstimationBundleData(
        estimation=CreateEstimationData(
            total_price=Decimal("1000000"),
            total_details=[CreateTotalDetailData(type="vật tư chính", name="Vật tư chính", price=Decimal("500000"))],
            estimation_work_items=[
                CreateEstimationWorkItemData(
                    name="Sơn lót tường",
                    item_id=None,
                    material_unit_price=Decimal("40000"),
                    labor_info=CreateLaborInfoData(
                        kn_manday=Decimal("2.5"),
                        processes=[CreateLaborInfoProcessData(name="Sơn lót lớp 1", kn_manday=Decimal("2"))],
                    ),
                    main_materials=[CreateMainMaterialData(product_name="VIETCOAT V-Silk")],
                ),
            ],
        ),
        sub_materials=[
            CreateSubMaterialData(
                type="vật tư phụ", name="Băng keo giấy", unit_price=Decimal("20000"),
                usages=[CreateItemSubData(item_id=None, amount=Decimal("5"), total_price=Decimal("100000"))],
            ),
        ],
        products_to_buy=[CreateProductToBuyData(product_name="VIETCOAT V-Silk", boxes_round=4)],
    )

    repo = SqlAlchemyEstimationRepository(db_session)
    repo.create(project_id=project.project_id, data=bundle)

    result = repo.get_by_project_id(project.project_id)
    assert result.total_price == Decimal("1000000")
    assert result.total_details[0].name == "Vật tư chính"
