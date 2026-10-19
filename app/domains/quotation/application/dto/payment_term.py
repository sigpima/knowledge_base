from decimal import Decimal

from dataclasses import dataclass


@dataclass
class CreatePaymentTermData:
    sequence: int
    percentage: Decimal | None = None
    trigger_type: str | None = None
    trigger_description: str | None = None


@dataclass
class PaymentTermData:
    payment_term_id: int
    sequence: int
    percentage: Decimal | None = None
    trigger_type: str | None = None
    trigger_description: str | None = None
