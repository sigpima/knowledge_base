from decimal import Decimal
from dataclasses import dataclass, field

from .labor_info import LaborInfoData, CreateLaborInfoData
from .main_material import MainMaterialData, CreateMainMaterialData


@dataclass
class EstimationWorkItemData:
    cost_item_id: int
    estimation_id: int
    item_id: int | None
    name: str
    main_unit_price: Decimal | None = None
    sub_unit_price: Decimal | None = None
    material_unit_price: Decimal | None = None
    total_price_area_based: Decimal | None = None
    total_price_round: Decimal | None = None
    material_unit_price_with_color_mixing_cost: Decimal | None = None
    labor_unit_price: Decimal | None = None
    profit_margin: Decimal | None = None
    labor_info: LaborInfoData | None = None
    main_materials: list[MainMaterialData] = field(default_factory=list)


@dataclass
class CreateEstimationWorkItemData:
    name: str
    item_id: int | None = None
    main_unit_price: Decimal | None = None
    sub_unit_price: Decimal | None = None
    material_unit_price: Decimal | None = None
    total_price_area_based: Decimal | None = None
    total_price_round: Decimal | None = None
    material_unit_price_with_color_mixing_cost: Decimal | None = None
    labor_unit_price: Decimal | None = None
    profit_margin: Decimal | None = None
    labor_info: CreateLaborInfoData | None = None
    main_materials: list[CreateMainMaterialData] = field(default_factory=list)
