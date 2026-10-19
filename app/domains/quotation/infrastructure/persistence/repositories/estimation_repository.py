from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.infrastructure.observability.logger import get_logger
from ....domain.repositories.estimation_repository import EstimationRepository
from ....application.dto import (
    EstimationData, TotalDetailData, EstimationWorkItemData,
    LaborInfoData, LaborInfoProcessData, MainMaterialData, LaborSummaryData,
    CostBreakdownItemData, CostBreakdownData, CreateEstimationBundleData,
)
from ..models import (
    EstimationModel, EstimationWorkItemModel, LaborInfoModel, LaborInfoProcessModel,
    MainMaterialModel, TotalDetailModel, SubMaterialModel, ItemSubModel, ProductToBuyModel,
    QuotationModel,
)

logger = get_logger(__name__)

# Used by both this repository's material_total/labor_total rollups and
# ProjectApplicationService.compare_cost_breakdown's "material"/"labor" cost_type shorthand --
# declared once here, imported there, never redefined.
MATERIAL_TOTAL_DETAIL_TYPES = {"vật tư chính", "vật tư phụ"}
LABOR_TOTAL_DETAIL_TYPES = {"nhân công"}


class SqlAlchemyEstimationRepository(EstimationRepository):

    def __init__(self, session: Session):
        self.session = session

    def create(self, project_id: int, data: CreateEstimationBundleData) -> None:
        try:
            estimation = EstimationModel(project_id=project_id, total_price=data.estimation.total_price)
            self.session.add(estimation)
            self.session.flush()

            for total_detail in data.estimation.total_details:
                self.session.add(TotalDetailModel(
                    estimation_id=estimation.estimation_id,
                    type=total_detail.type,
                    name=total_detail.name,
                    price=total_detail.price,
                ))

            for work_item in data.estimation.estimation_work_items:
                cost_item = EstimationWorkItemModel(
                    estimation_id=estimation.estimation_id,
                    item_id=work_item.item_id,
                    name=work_item.name,
                    main_unit_price=work_item.main_unit_price,
                    sub_unit_price=work_item.sub_unit_price,
                    material_unit_price=work_item.material_unit_price,
                    total_price_area_based=work_item.total_price_area_based,
                    total_price_round=work_item.total_price_round,
                    material_unit_price_with_color_mixing_cost=work_item.material_unit_price_with_color_mixing_cost,
                    labor_unit_price=work_item.labor_unit_price,
                    profit_margin=work_item.profit_margin,
                )
                self.session.add(cost_item)
                self.session.flush()

                if work_item.labor_info is not None:
                    labor_info = LaborInfoModel(
                        cost_item_id=cost_item.cost_item_id,
                        area=work_item.labor_info.area,
                        kn_manday=work_item.labor_info.kn_manday,
                        main_out_manday=work_item.labor_info.main_out_manday,
                        sub_out_manday=work_item.labor_info.sub_out_manday,
                        kn_total_price=work_item.labor_info.kn_total_price,
                        main_out_total_price=work_item.labor_info.main_out_total_price,
                        sub_out_total_price=work_item.labor_info.sub_out_total_price,
                        kn_out_total_price=work_item.labor_info.kn_out_total_price,
                        final_unit_price_type=work_item.labor_info.final_unit_price_type,
                        labor_coeff=work_item.labor_info.labor_coeff,
                        labor_unit_price=work_item.labor_info.labor_unit_price,
                    )
                    self.session.add(labor_info)
                    self.session.flush()

                    for process in work_item.labor_info.processes:
                        self.session.add(LaborInfoProcessModel(
                            labor_id=labor_info.labor_id,
                            name=process.name,
                            main_labors_kn=process.main_labors_kn,
                            main_labors_out=process.main_labors_out,
                            sub_labors_out=process.sub_labors_out,
                            days=process.days,
                            kn_manday=process.kn_manday,
                            main_out_manday=process.main_out_manday,
                            sub_out_manday=process.sub_out_manday,
                        ))

                for material in work_item.main_materials:
                    self.session.add(MainMaterialModel(
                        cost_item_id=cost_item.cost_item_id,
                        product_segment=material.product_segment,
                        product_line=material.product_line,
                        product_name=material.product_name,
                        layers=material.layers,
                        package_type=material.package_type,
                        theoretical_rate=material.theoretical_rate,
                        construction_loss=material.construction_loss,
                        actual_rate_per_litter=material.actual_rate_per_litter,
                        actual_rate_per_box=material.actual_rate_per_box,
                        box_price=material.box_price,
                        color_mixing_price=material.color_mixing_price,
                        unit_price_per_m2=material.unit_price_per_m2,
                        percent_usage=material.percent_usage,
                        area=material.area,
                        total_price_area_based=material.total_price_area_based,
                        litters=material.litters,
                        boxes=material.boxes,
                        total_price_round=material.total_price_round,
                    ))

            for sub_material in data.sub_materials:
                sub_material_model = SubMaterialModel(
                    project_id=project_id,
                    type=sub_material.type,
                    name=sub_material.name,
                    unit=sub_material.unit,
                    unit_price=sub_material.unit_price,
                    total_price=sub_material.total_price,
                )
                self.session.add(sub_material_model)
                self.session.flush()

                for usage in sub_material.usages:
                    self.session.add(ItemSubModel(
                        item_id=usage.item_id,
                        sub_id=sub_material_model.sub_id,
                        amount=usage.amount,
                        total_price=usage.total_price,
                    ))

            for product in data.products_to_buy:
                self.session.add(ProductToBuyModel(
                    project_id=project_id,
                    product_name=product.product_name,
                    package_type=product.package_type,
                    boxes=product.boxes,
                    boxes_round=product.boxes_round,
                    boxes_price=product.boxes_price,
                    boxes_unit_price=product.boxes_unit_price,
                    mini_package_type=product.mini_package_type,
                    mini_boxes_round=product.mini_boxes_round,
                    mini_boxes_price=product.mini_boxes_price,
                    mini_boxes_unit_price=product.mini_boxes_unit_price,
                    total_price_round=product.total_price_round,
                ))

            self.session.commit()
        except Exception:
            logger.error("Failed to write dự toán bundle for project_id=%r", project_id, exc_info=True)
            self.session.rollback()
            raise

    def get_by_project_id(self, project_id: int) -> EstimationData | None:
        model = (
            self.session.query(EstimationModel)
            .filter(EstimationModel.project_id == project_id)
            .one_or_none()
        )
        if model is None:
            return None

        total_kn, total_main_out, total_sub_out = (
            self.session.query(
                func.coalesce(func.sum(LaborInfoModel.kn_manday), 0),
                func.coalesce(func.sum(LaborInfoModel.main_out_manday), 0),
                func.coalesce(func.sum(LaborInfoModel.sub_out_manday), 0),
            )
            .join(EstimationWorkItemModel, LaborInfoModel.cost_item_id == EstimationWorkItemModel.cost_item_id)
            .filter(EstimationWorkItemModel.estimation_id == model.estimation_id)
            .one()
        )
        total_out = total_main_out + total_sub_out
        labor_summary = LaborSummaryData(
            total_kn_manday=total_kn,
            total_main_out_manday=total_main_out,
            total_sub_out_manday=total_sub_out,
            total_out_manday=total_out,
            total_manday=total_kn + total_out,
        )

        quotation_total_amount = (
            self.session.query(func.coalesce(func.sum(QuotationModel.total_amount), 0))
            .filter(QuotationModel.project_id == project_id)
            .scalar()
        )

        breakdown_totals: dict[str, Decimal] = {}
        for d in model.total_details:
            breakdown_totals[d.type] = breakdown_totals.get(d.type, Decimal("0")) + d.price

        def _pct(price: Decimal) -> Decimal | None:
            if not quotation_total_amount:
                return None
            return (price / quotation_total_amount * 100).quantize(Decimal("0.01"))

        by_type = [
            CostBreakdownItemData(type=t, price=p, pct_of_quotation_total=_pct(p))
            for t, p in breakdown_totals.items()
        ]
        material_total = sum(
            (p for t, p in breakdown_totals.items() if t.strip().lower() in MATERIAL_TOTAL_DETAIL_TYPES),
            Decimal("0"),
        )
        labor_total = sum(
            (p for t, p in breakdown_totals.items() if t.strip().lower() in LABOR_TOTAL_DETAIL_TYPES),
            Decimal("0"),
        )
        cost_breakdown = CostBreakdownData(
            quotation_total_amount=quotation_total_amount,
            material_total=material_total,
            material_pct=_pct(material_total),
            labor_total=labor_total,
            labor_pct=_pct(labor_total),
            by_type=by_type,
        )

        return EstimationData(
            estimation_id=model.estimation_id,
            project_id=model.project_id,
            total_price=model.total_price,
            total_details=[
                TotalDetailData(
                    total_detail_id=d.total_detail_id,
                    type=d.type,
                    name=d.name,
                    price=d.price,
                )
                for d in model.total_details
            ],
            labor_summary=labor_summary,
            cost_breakdown=cost_breakdown,
        )

    def get_work_item_detail(self, item_id: int) -> EstimationWorkItemData | None:
        model = (
            self.session.query(EstimationWorkItemModel)
            .filter(EstimationWorkItemModel.item_id == item_id)
            .one_or_none()
        )
        if model is None:
            return None
        return self._to_data(model)

    def _to_data(self, model: EstimationWorkItemModel) -> EstimationWorkItemData:
        labor_info = None
        if model.labor_info is not None:
            main_out_unit_price = None
            if model.labor_info.main_out_manday and model.labor_info.main_out_total_price is not None:
                main_out_unit_price = (
                    model.labor_info.main_out_total_price / model.labor_info.main_out_manday
                ).quantize(Decimal("0.01"))

            sub_out_unit_price = None
            if model.labor_info.sub_out_manday and model.labor_info.sub_out_total_price is not None:
                sub_out_unit_price = (
                    model.labor_info.sub_out_total_price / model.labor_info.sub_out_manday
                ).quantize(Decimal("0.01"))

            labor_info = LaborInfoData(
                labor_id=model.labor_info.labor_id,
                cost_item_id=model.labor_info.cost_item_id,
                area=model.labor_info.area,
                kn_manday=model.labor_info.kn_manday,
                main_out_manday=model.labor_info.main_out_manday,
                sub_out_manday=model.labor_info.sub_out_manday,
                kn_total_price=model.labor_info.kn_total_price,
                main_out_total_price=model.labor_info.main_out_total_price,
                sub_out_total_price=model.labor_info.sub_out_total_price,
                kn_out_total_price=model.labor_info.kn_out_total_price,
                final_unit_price_type=model.labor_info.final_unit_price_type,
                labor_coeff=model.labor_info.labor_coeff,
                labor_unit_price=model.labor_info.labor_unit_price,
                main_out_unit_price=main_out_unit_price,
                sub_out_unit_price=sub_out_unit_price,
                processes=[
                    LaborInfoProcessData(
                        process_id=p.process_id,
                        labor_id=p.labor_id,
                        name=p.name,
                        main_labors_kn=p.main_labors_kn,
                        main_labors_out=p.main_labors_out,
                        sub_labors_out=p.sub_labors_out,
                        days=p.days,
                        kn_manday=p.kn_manday,
                        main_out_manday=p.main_out_manday,
                        sub_out_manday=p.sub_out_manday,
                    )
                    for p in model.labor_info.processes
                ],
            )

        return EstimationWorkItemData(
            cost_item_id=model.cost_item_id,
            estimation_id=model.estimation_id,
            item_id=model.item_id,
            name=model.name,
            main_unit_price=model.main_unit_price,
            sub_unit_price=model.sub_unit_price,
            material_unit_price=model.material_unit_price,
            total_price_area_based=model.total_price_area_based,
            total_price_round=model.total_price_round,
            material_unit_price_with_color_mixing_cost=model.material_unit_price_with_color_mixing_cost,
            labor_unit_price=model.labor_unit_price,
            profit_margin=model.profit_margin,
            labor_info=labor_info,
            main_materials=[
                MainMaterialData(
                    main_material_id=m.main_material_id,
                    cost_item_id=m.cost_item_id,
                    product_segment=m.product_segment,
                    product_line=m.product_line,
                    product_name=m.product_name,
                    layers=m.layers,
                    package_type=m.package_type,
                    theoretical_rate=m.theoretical_rate,
                    construction_loss=m.construction_loss,
                    actual_rate_per_litter=m.actual_rate_per_litter,
                    actual_rate_per_box=m.actual_rate_per_box,
                    box_price=m.box_price,
                    color_mixing_price=m.color_mixing_price,
                    unit_price_per_m2=m.unit_price_per_m2,
                    percent_usage=m.percent_usage,
                    area=m.area,
                    total_price_area_based=m.total_price_area_based,
                    litters=m.litters,
                    boxes=m.boxes,
                    total_price_round=m.total_price_round,
                )
                for m in model.main_materials
            ],
        )
