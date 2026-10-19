from decimal import Decimal

from dataclasses import dataclass


@dataclass
class CreateScopeTermData:
    scope_type: str
    term_type: str
    description: str
    amount: Decimal | None = None


@dataclass
class ScopeTermData:
    scope_term_id: int
    scope_type: str
    term_type: str
    description: str
    amount: Decimal | None = None
