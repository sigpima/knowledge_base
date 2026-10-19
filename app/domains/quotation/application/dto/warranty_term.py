from decimal import Decimal

from dataclasses import dataclass


@dataclass
class CreateWarrantyTermData:
    period: int | None = None
    period_unit: str | None = None
    extend_percent: Decimal | None = None
    extend_period: int | None = None


@dataclass
class WarrantyTermData:
    warranty_term_id: int
    period: int | None = None
    period_unit: str | None = None
    extend_percent: Decimal | None = None
    extend_period: int | None = None
