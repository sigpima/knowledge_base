from decimal import Decimal
from dataclasses import dataclass, field

from .labor_info_process import LaborInfoProcessData, CreateLaborInfoProcessData


@dataclass
class LaborInfoData:
    labor_id: int
    cost_item_id: int
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
    main_out_unit_price: Decimal | None = None
    sub_out_unit_price: Decimal | None = None
    processes: list[LaborInfoProcessData] = field(default_factory=list)


@dataclass
class CreateLaborInfoData:
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
    processes: list[CreateLaborInfoProcessData] = field(default_factory=list)
