"""Cấu trúc file YAML báo giá (một file = một công trình), dùng Pydantic để kiểm tra.

Tên trường bám đúng các DTO `Create*Data` hiện có để mapper chỉ là phép gán.
Mô tả đầy đủ cho người dùng: docs/data-format.md.
"""
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConceptRef(_Spec):
    type: str
    name: str


class StepSpec(_Spec):
    name: str
    description: str | None = None
    product_name: str | None = None
    layers: int | None = None
    note: str | None = None


class WorkItemSpec(_Spec):
    key: str = Field(min_length=1)
    name: str
    description: str | None = None
    unit: str
    quantity: Decimal
    unit_price: Decimal
    concepts: list[ConceptRef] = []
    steps: list[StepSpec] = []


class PackageSpec(_Spec):
    name: str
    work_items: list[WorkItemSpec]


class ScopeTermSpec(_Spec):
    scope_type: str
    term_type: str
    description: str
    amount: Decimal | None = None


class PaymentTermSpec(_Spec):
    percentage: Decimal | None = None
    trigger_type: str | None = None
    trigger_description: str | None = None


class WarrantySpec(_Spec):
    period: int | None = None
    period_unit: str | None = None
    extend_percent: Decimal | None = None
    extend_period: int | None = None


class QuotationSpec(_Spec):
    code: str
    issue_date: date | None = None
    currency: str = "VND"
    total_amount: Decimal | None = None
    packages: list[PackageSpec]
    scope_terms: list[ScopeTermSpec] = []
    payment_terms: list[PaymentTermSpec] = []
    warranty: WarrantySpec | None = None


class ProjectSpec(_Spec):
    name: str
    address: str
    estimated_workdays: list[int] | None = None


class ExtraSpec(_Spec):
    issue_date: date | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    description: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    metadata: dict[str, Any] = {}


class TotalDetailSpec(_Spec):
    type: str
    name: str
    price: Decimal


class LaborProcessSpec(_Spec):
    name: str
    main_labors_kn: int | None = None
    main_labors_out: int | None = None
    sub_labors_out: int | None = None
    days: Decimal | None = None
    kn_manday: Decimal | None = None
    main_out_manday: Decimal | None = None
    sub_out_manday: Decimal | None = None


class LaborSpec(_Spec):
    area: Decimal | None = None
    kn_manday: Decimal | None = None
    main_out_manday: Decimal | None = None
    sub_out_manday: Decimal | None = None
    kn_total_price: Decimal | None = None
    main_out_total_price: Decimal | None = None
    sub_out_total_price: Decimal | None = None
    kn_out_total_price: Decimal | None = None
    final_unit_price_type: str | None = None
    labor_coeff: Decimal | None = None
    labor_unit_price: Decimal | None = None
    processes: list[LaborProcessSpec] = []


class MainMaterialSpec(_Spec):
    product_segment: str | None = None
    product_line: str | None = None
    product_name: str | None = None
    layers: int | None = None
    package_type: str | None = None
    theoretical_rate: Decimal | None = None
    construction_loss: Decimal | None = None
    actual_rate_per_litter: Decimal | None = None
    actual_rate_per_box: Decimal | None = None
    box_price: Decimal | None = None
    color_mixing_price: Decimal | None = None
    unit_price_per_m2: Decimal | None = None
    percent_usage: Decimal | None = None
    area: Decimal | None = None
    total_price_area_based: Decimal | None = None
    litters: Decimal | None = None
    boxes: Decimal | None = None
    total_price_round: Decimal | None = None


class EstimationItemSpec(_Spec):
    name: str
    work_item: str | None = None
    main_unit_price: Decimal | None = None
    sub_unit_price: Decimal | None = None
    material_unit_price: Decimal | None = None
    total_price_area_based: Decimal | None = None
    total_price_round: Decimal | None = None
    material_unit_price_with_color_mixing_cost: Decimal | None = None
    labor_unit_price: Decimal | None = None
    profit_margin: Decimal | None = None
    labor: LaborSpec | None = None
    main_materials: list[MainMaterialSpec] = []


class SubMaterialUsageSpec(_Spec):
    work_item: str | None = None
    amount: Decimal | None = None
    total_price: Decimal | None = None


class SubMaterialSpec(_Spec):
    type: str
    name: str
    unit: str | None = None
    unit_price: Decimal | None = None
    total_price: Decimal | None = None
    usages: list[SubMaterialUsageSpec] = []


class ProductToBuySpec(_Spec):
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


class EstimationSpec(_Spec):
    total_price: Decimal | None = None
    total_details: list[TotalDetailSpec] = []
    items: list[EstimationItemSpec] = []
    sub_materials: list[SubMaterialSpec] = []
    products_to_buy: list[ProductToBuySpec] = []


class QuotationFile(_Spec):
    project: ProjectSpec
    quotation: QuotationSpec
    extras: list[ExtraSpec] = []
    estimation: EstimationSpec | None = None
