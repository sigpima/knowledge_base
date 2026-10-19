from decimal import Decimal

from app.domains.quotation.application.dto import (
    EstimationData,
    TotalDetailData,
    EstimationWorkItemData,
    LaborInfoData,
    LaborInfoProcessData,
    MainMaterialData,
)


def test_estimation_data_nests_total_details():
    estimation = EstimationData(
        estimation_id=1,
        project_id=1,
        total_price=Decimal("285634855.25"),
        total_details=[
            TotalDetailData(total_detail_id=1, type="vật tư chính", name="vật tư chính", price=Decimal("100")),
        ],
    )
    assert estimation.total_details[0].type == "vật tư chính"


def test_labor_info_data_nests_processes():
    labor = LaborInfoData(
        labor_id=1,
        cost_item_id=1,
        final_unit_price_type="has_kn",
        labor_unit_price=Decimal("181980.37"),
        processes=[
            LaborInfoProcessData(process_id=1, labor_id=1, name="Chống thấm 2 lớp"),
        ],
    )
    assert labor.processes[0].name == "Chống thấm 2 lớp"


def test_estimation_work_item_data_nests_labor_and_materials():
    item = EstimationWorkItemData(
        cost_item_id=1,
        estimation_id=1,
        item_id=None,
        name="Hạng mục 1",
        labor_info=None,
        main_materials=[
            MainMaterialData(main_material_id=1, cost_item_id=1, product_name="VIETCOAT SEAL-11A PLUS SÀN"),
        ],
    )
    assert item.main_materials[0].product_name == "VIETCOAT SEAL-11A PLUS SÀN"
