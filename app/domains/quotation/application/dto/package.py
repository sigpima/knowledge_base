from decimal import Decimal

from dataclasses import dataclass, field

from .work_item import WorkItemData, CreateWorkItemData


@dataclass
class CreateQuotationPackageData:
    name: str
    sequence: int
    total_amount: Decimal | None = None
    work_items: list[CreateWorkItemData] = field(default_factory=list)


@dataclass
class QuotationPackageData:
    package_id: int
    name: str
    sequence: int
    total_amount: Decimal | None = None
    work_items: list[WorkItemData] = field(default_factory=list)
