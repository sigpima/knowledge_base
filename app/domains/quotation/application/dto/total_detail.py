from decimal import Decimal
from dataclasses import dataclass


@dataclass
class TotalDetailData:
    total_detail_id: int
    type: str
    name: str
    price: Decimal


@dataclass
class CreateTotalDetailData:
    type: str
    name: str
    price: Decimal
