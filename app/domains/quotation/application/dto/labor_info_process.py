from decimal import Decimal
from dataclasses import dataclass


@dataclass
class LaborInfoProcessData:
    process_id: int
    labor_id: int
    name: str
    main_labors_kn: int | None = None
    main_labors_out: int | None = None
    sub_labors_out: int | None = None
    days: Decimal | None = None
    kn_manday: Decimal | None = None
    main_out_manday: Decimal | None = None
    sub_out_manday: Decimal | None = None


@dataclass
class CreateLaborInfoProcessData:
    name: str
    main_labors_kn: int | None = None
    main_labors_out: int | None = None
    sub_labors_out: int | None = None
    days: Decimal | None = None
    kn_manday: Decimal | None = None
    main_out_manday: Decimal | None = None
    sub_out_manday: Decimal | None = None
