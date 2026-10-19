from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Quantity:
    value: Decimal
    unit: str

    def __post_init__(self):
        if not self.unit:
            raise ValueError("Quantity.unit must not be empty")
