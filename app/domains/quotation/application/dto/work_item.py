from decimal import Decimal

from dataclasses import dataclass, field

from .concept import ConceptData, CreateConceptData
from .work_step import WorkStepData, CreateWorkStepData


@dataclass
class CreateWorkItemData:
    name: str
    description: str | None
    unit: str
    unit_price: Decimal
    quantity: Decimal
    currency: str
    work_steps: list[CreateWorkStepData] = field(default_factory=list)
    concepts: list[CreateConceptData] = field(default_factory=list)


@dataclass
class WorkItemData:
    item_id: int
    name: str
    sequence: int
    description: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    currency: str | None = None
    total_price: Decimal | None = None
    concepts: list[ConceptData] = field(default_factory=list)
    work_steps: list[WorkStepData] = field(default_factory=list)
