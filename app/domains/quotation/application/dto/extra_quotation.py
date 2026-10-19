from datetime import date
from decimal import Decimal
from typing import Any

from dataclasses import dataclass, field


@dataclass
class CreateExtraQuotationData:
    issue_date: date | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    description: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtraQuotationData:
    extra_quotation_id: int
    issue_date: date | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    description: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
