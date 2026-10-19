from decimal import Decimal
from dataclasses import dataclass, field

from .total_detail import TotalDetailData, CreateTotalDetailData
from .labor_summary import LaborSummaryData
from .cost_breakdown import CostBreakdownData
from .estimation_work_item import CreateEstimationWorkItemData


@dataclass
class EstimationData:
    estimation_id: int
    project_id: int
    total_price: Decimal | None = None
    total_details: list[TotalDetailData] = field(default_factory=list)
    labor_summary: LaborSummaryData | None = None
    cost_breakdown: CostBreakdownData | None = None


@dataclass
class CreateEstimationData:
    total_price: Decimal | None = None
    total_details: list[CreateTotalDetailData] = field(default_factory=list)
    estimation_work_items: list[CreateEstimationWorkItemData] = field(default_factory=list)


@dataclass
class CreateItemSubData:
    item_id: int | None = None
    amount: Decimal | None = None
    total_price: Decimal | None = None


@dataclass
class CreateSubMaterialData:
    type: str
    name: str
    unit: str | None = None
    unit_price: Decimal | None = None
    total_price: Decimal | None = None
    usages: list[CreateItemSubData] = field(default_factory=list)


@dataclass
class CreateProductToBuyData:
    product_name: str
    package_type: str | None = None
    boxes: Decimal | None = None
    boxes_round: int | None = None
    boxes_price: Decimal | None = None
    boxes_unit_price: Decimal | None = None
    mini_package_type: str | None = None
    mini_boxes_round: int | None = None
    mini_boxes_price: Decimal | None = None
    mini_boxes_unit_price: Decimal | None = None
    total_price_round: Decimal | None = None


@dataclass
class CreateEstimationBundleData:
    estimation: CreateEstimationData
    sub_materials: list[CreateSubMaterialData] = field(default_factory=list)
    products_to_buy: list[CreateProductToBuyData] = field(default_factory=list)
