from datetime import date
from decimal import Decimal
from typing import Any

from dataclasses import dataclass, field

from .package import CreateQuotationPackageData, QuotationPackageData


@dataclass
class CreateQuotationData:
    quotation_code: str
    project_name: str | None = None
    project_address: str | None = None
    issue_date: date | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    packages: list[CreateQuotationPackageData] = field(default_factory=list)


@dataclass
class QuotationData:
    quotation_id: int
    quotation_code: str
    project_name: str | None = None
    project_address: str | None = None
    issue_date: date | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    packages: list[QuotationPackageData] = field(default_factory=list)
