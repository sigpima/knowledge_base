from decimal import Decimal
from dataclasses import dataclass, field


@dataclass
class CostBreakdownItemData:
    type: str
    price: Decimal
    pct_of_quotation_total: Decimal | None


@dataclass
class CostBreakdownData:
    quotation_total_amount: Decimal
    material_total: Decimal
    material_pct: Decimal | None
    labor_total: Decimal
    labor_pct: Decimal | None
    by_type: list[CostBreakdownItemData] = field(default_factory=list)
