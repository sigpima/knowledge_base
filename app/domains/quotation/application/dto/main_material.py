from decimal import Decimal
from dataclasses import dataclass


@dataclass
class MainMaterialData:
    main_material_id: int
    cost_item_id: int
    product_segment: str | None = None
    product_line: str | None = None
    product_name: str | None = None
    layers: int | None = None
    package_type: str | None = None
    theoretical_rate: Decimal | None = None
    construction_loss: Decimal | None = None
    actual_rate_per_litter: Decimal | None = None
    actual_rate_per_box: Decimal | None = None
    box_price: Decimal | None = None
    color_mixing_price: Decimal | None = None
    unit_price_per_m2: Decimal | None = None
    percent_usage: Decimal | None = None
    area: Decimal | None = None
    total_price_area_based: Decimal | None = None
    litters: Decimal | None = None
    boxes: Decimal | None = None
    total_price_round: Decimal | None = None


@dataclass
class CreateMainMaterialData:
    product_segment: str | None = None
    product_line: str | None = None
    product_name: str | None = None
    layers: int | None = None
    package_type: str | None = None
    theoretical_rate: Decimal | None = None
    construction_loss: Decimal | None = None
    actual_rate_per_litter: Decimal | None = None
    actual_rate_per_box: Decimal | None = None
    box_price: Decimal | None = None
    color_mixing_price: Decimal | None = None
    unit_price_per_m2: Decimal | None = None
    percent_usage: Decimal | None = None
    area: Decimal | None = None
    total_price_area_based: Decimal | None = None
    litters: Decimal | None = None
    boxes: Decimal | None = None
    total_price_round: Decimal | None = None
