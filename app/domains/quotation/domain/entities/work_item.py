from dataclasses import dataclass, field
from typing import List, Optional

from .concept import Concept
from .work_step import WorkStep
from ..value_objects.money import Money
from ..value_objects.quantity import Quantity


@dataclass
class WorkItem:
    package_id: int
    sequence: int
    name: str
    description: str
    quantity: Quantity
    unit_price: Money
    work_steps: List["WorkStep"] = field(default_factory=list)
    concepts: List["Concept"] = field(default_factory=list)
    item_id: Optional[int] = None

    @property
    def total_price(self) -> Money:
        return Money(self.quantity.value * self.unit_price.amount, self.unit_price.currency)
