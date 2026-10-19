from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "VND"

    def __post_init__(self):
        if not self.currency:
            raise ValueError("Money.currency must not be empty")

    def __add__(self, other: "Money") -> "Money":
        if other.currency != self.currency:
            raise ValueError(
                f"Cannot add Money in different currencies: {self.currency} vs {other.currency}"
            )
        return Money(self.amount + other.amount, self.currency)
