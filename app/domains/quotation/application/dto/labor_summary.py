from decimal import Decimal
from dataclasses import dataclass


@dataclass
class LaborSummaryData:
    total_kn_manday: Decimal
    total_main_out_manday: Decimal
    total_sub_out_manday: Decimal
    total_out_manday: Decimal
    total_manday: Decimal
