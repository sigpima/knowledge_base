from decimal import Decimal

from app.domains.quotation.application.dto import (
    CreateEstimationBundleData, CreateEstimationData, CreateTotalDetailData,
    CreateEstimationWorkItemData, CreateLaborInfoData, CreateLaborInfoProcessData,
    CreateMainMaterialData, CreateSubMaterialData, CreateItemSubData, CreateProductToBuyData,
)


def test_create_estimation_bundle_data_constructs_with_full_nesting():
    bundle = CreateEstimationBundleData(
        estimation=CreateEstimationData(
            total_price=Decimal("1000000"),
            total_details=[CreateTotalDetailData(type="vật tư chính", name="Vật tư chính", price=Decimal("500000"))],
            estimation_work_items=[
                CreateEstimationWorkItemData(
                    name="Sơn lót tường",
                    item_id=42,
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
                type="vật tư phụ", name="Băng keo giấy",
                usages=[CreateItemSubData(item_id=42, amount=Decimal("5"))],
            ),
        ],
        products_to_buy=[CreateProductToBuyData(product_name="VIETCOAT V-Silk", boxes_round=4)],
    )

    assert bundle.estimation.estimation_work_items[0].labor_info.processes[0].name == "Sơn lót lớp 1"
    assert bundle.sub_materials[0].usages[0].item_id == 42
    assert bundle.products_to_buy[0].boxes_round == 4
