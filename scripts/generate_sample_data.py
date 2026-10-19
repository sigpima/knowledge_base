"""Sinh bộ file báo giá YAML giả (công trình sơn) vào `data/sample/`.

    python scripts/generate_sample_data.py --out data/sample

Tất định: cùng `SEED` luôn cho cùng kết quả. Cách làm "khớp theo cấu trúc": chọn vài trường
gốc ngẫu nhiên (diện tích, giá thùng, số thợ, định mức) rồi suy ra mọi tổng, nên các con số
luôn khớp nhau mà không cần bước kiểm tra sau.

Bảy công trình "kịch bản" được đặt cố định để các câu hỏi mẫu trong README có đáp án rõ;
phần còn lại là ngẫu nhiên có seed. Mọi tên là bịa (xem scripts/fake_catalog.py).
"""
import argparse
import math
import random
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import yaml

from scripts.fake_catalog import (
    BUILDING_TYPES,
    PAYMENT_TRIGGERS,
    PLACES,
    PREP_STEPS,
    PROCESS_KIND,
    PROCESS_POOLS,
    PROJECT_NAMES,
    SCOPE_ENTRIES,
    STREETS,
    SUB_MATERIAL_CATALOG,
    WORK_ITEM_CATALOG,
    CatalogItem,
)

SEED = 20261020
RANDOM_PROJECT_COUNT = 17
WATERPROOF = "Chống thấm sân thượng"
FILE_HEADER = (
    "# Dữ liệu giả lập do scripts/generate_sample_data.py sinh ra.\n"
    "# Mọi tên công ty, công trình, sản phẩm đều là bịa; số liệu không lấy từ nguồn thật nào.\n"
)


def D(value, places: str = "0.01") -> Decimal:
    return Decimal(str(value)).quantize(Decimal(places), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ItemPin:
    """Cố định một hạng mục của công trình kịch bản để so sánh được hai công trình với nhau."""

    area: int
    segment: str
    box_price: int
    steps: tuple[str, ...]
    intensity: float  # ngày công trên m2 cho mỗi bước
    workers: tuple[int, int, int]  # thợ nhà, thợ chính thuê ngoài, thợ phụ thuê ngoài (mỗi bước)


@dataclass(frozen=True)
class Scenario:
    key: str
    building: str
    base_name: str
    street: str
    place: str
    rates: tuple[int, int, int] | None = None  # đơn giá ngày công: thợ nhà, chính thuê ngoài, phụ thuê ngoài
    worker_profile: str = "standard"  # standard | outsourced | inhouse
    labor_factor: float = 1.0
    final_type: str | None = None
    has_estimation: bool = True
    has_extras: bool | None = None  # None = ngẫu nhiên
    stepless_item: bool = False
    pins: dict[str, ItemPin] = field(default_factory=dict)
    n_items: int = 5


_WATERPROOF_STEPS = ("Xử lý bề mặt", "Chống thấm lớp 1", "Chống thấm lớp 2")

SCENARIO_LIST = [
    # Cặp A/B: cùng quy mô, cùng nhân công, chênh đơn giá chống thấm do VẬT TƯ.
    Scenario(
        "bietthu-sen-vang", "Biệt thự", "Sen Vàng", "Nguyễn Huệ", "Quận 7, TP.HCM",
        rates=(360_000, 480_000, 320_000), labor_factor=1.0, n_items=4,
        pins={WATERPROOF: ItemPin(180, "CAO CẤP", 1_550_000, _WATERPROOF_STEPS, 0.03, (2, 0, 1))},
    ),
    Scenario(
        "bietthu-lua-non", "Biệt thự", "Lúa Non", "Lê Lợi", "Quận 7, TP.HCM",
        rates=(360_000, 480_000, 320_000), labor_factor=1.0, n_items=4,
        pins={WATERPROOF: ItemPin(190, "TRUNG CẤP", 820_000, _WATERPROOF_STEPS, 0.03, (2, 0, 1))},
    ),
    # Cặp C/D: cùng vật tư, chênh đơn giá chống thấm do NHÂN CÔNG thuê ngoài.
    Scenario(
        "nhapho-bach-duong", "Nhà phố", "Bạch Dương", "Trần Hưng Đạo", "Bình Thạnh, TP.HCM",
        rates=(360_000, 560_000, 380_000), worker_profile="outsourced", final_type="all_out", n_items=4,
        pins={WATERPROOF: ItemPin(175, "TRUNG CẤP", 820_000, _WATERPROOF_STEPS, 0.06, (0, 3, 3))},
    ),
    Scenario(
        "nhapho-lien-hoa", "Nhà phố", "Liên Hoa", "Hai Bà Trưng", "Bình Thạnh, TP.HCM",
        rates=(330_000, 480_000, 320_000), worker_profile="inhouse", final_type="has_kn", n_items=4,
        pins={WATERPROOF: ItemPin(185, "TRUNG CẤP", 820_000, _WATERPROOF_STEPS, 0.03, (3, 0, 1))},
    ),
    # Tỷ trọng nhân công cao bất thường.
    Scenario(
        "vanphong-ngoc-lan", "Văn phòng", "Ngọc Lan", "Điện Biên Phủ", "Quận 1, TP.HCM",
        labor_factor=3.2, n_items=6,
    ),
    # Chưa có dự toán.
    Scenario(
        "nhaxuong-thanh-cong", "Nhà xưởng", "Thành Công", "Quang Trung", "Bình Dương",
        has_estimation=False, n_items=4,
    ),
    # Không có phát sinh, có một hạng mục chưa khai bước thi công.
    Scenario(
        "truong-anh-sao", "Trường học", "Ánh Sao", "Nguyễn Văn Linh", "TP. Đà Nẵng",
        has_extras=False, stepless_item=True, n_items=5,
    ),
]
SCENARIOS: dict[str, Scenario] = {s.key: s for s in SCENARIO_LIST}


# --------------------------------------------------------------------------- YAML output


class _Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data):  # luôn ghi giá trị đầy đủ; loader không chấp nhận alias
        return True


def _represent_decimal(dumper: yaml.SafeDumper, value: Decimal):
    if value == value.to_integral_value():
        return dumper.represent_int(int(value))
    return dumper.represent_scalar("tag:yaml.org,2002:float", format(value.normalize(), "f"))


_Dumper.add_representer(Decimal, _represent_decimal)


def _drop_none(value):
    if isinstance(value, dict):
        return {k: _drop_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_drop_none(v) for v in value]
    return value


def dump_yaml(data: dict) -> str:
    body = yaml.dump(
        _drop_none(data), Dumper=_Dumper, allow_unicode=True, sort_keys=False, width=120, default_flow_style=False
    )
    return (FILE_HEADER if "project" in data else "") + body


# --------------------------------------------------------------------------- helpers


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn").lower()
    return "-".join("".join(c if c.isalnum() else " " for c in text).split())


def _step(name: str, main_materials: list[dict], rng: random.Random) -> dict:
    """Bước chuẩn bị bề mặt không có sản phẩm; bước còn lại dùng sản phẩm chính của hạng mục."""
    if name in PREP_STEPS:
        return dict(name=name)
    row = rng.choice(main_materials)
    layers = 1 if "lớp" in name else row["layers"]
    return dict(name=name, product_name=row["product_name"], layers=layers)


def _workers_for(profile: str, rng: random.Random) -> tuple[int, int, int]:
    if profile == "outsourced":
        return 0, rng.randint(2, 4), rng.randint(2, 4)
    if profile == "inhouse":
        return rng.randint(2, 4), 0, rng.randint(0, 1)
    return rng.randint(0, 3), rng.randint(0, 2), rng.randint(1, 4)


@dataclass
class _ProjectContext:
    rates: tuple[Decimal, Decimal, Decimal]
    coeff: Decimal
    labor_factor: float
    profile: str
    final_type: str | None


def _build_item(rng, entry: CatalogItem, index: int, ctx: _ProjectContext, pin: ItemPin | None, stepless: bool):
    """Trả về (work_item_dict, estimation_item_dict, tổng thành phần để cộng lên cấp công trình)."""
    area = D(pin.area if pin else rng.uniform(*entry.area))
    key = f"hm{index:02d}-{_slug(entry.name)}"

    # ---- vật tư chính ----
    if pin:
        rows_spec = [(next(p for p in entry.products if p[0] == pin.segment), Decimal(1), pin.box_price)]
    else:
        weights = [rng.uniform(0.5, 1.5) for _ in range(rng.randint(1, 3))]
        total_w = sum(weights)
        rows_spec = []
        for w in weights:
            product = rng.choices(entry.products, weights=[0.7, 0.3])[0]  # phần lớn dùng dòng trung cấp
            low, high = entry.box_price[product[0]]
            rows_spec.append((product, D(w / total_w, "0.0001"), rng.randint(low // 1000, high // 1000) * 1000))

    main_materials, boxes_by_product = [], {}
    tpab_sum = tpr_sum = color_total = Decimal(0)
    for product, share, box_price in rows_spec:
        segment, line, product_name = product
        coverage = D(rng.uniform(*entry.coverage), "0.01")
        loss = D(rng.uniform(0.03, 0.12), "0.0001")
        per_litre = D(coverage * (1 - loss))
        liters = rng.choice(entry.box_liters)
        per_box = D(per_litre * liters)
        layers = rng.choice(entry.layers)
        boxes = D(area * layers * share / per_box)
        boxes_round = max(1, math.ceil(boxes))
        color = Decimal(0 if pin else rng.choice([0, 0, 15_000, 25_000, 40_000]))
        row = dict(
            product_segment=segment, product_line=line, product_name=product_name, layers=layers,
            package_type=f"{liters}L/thùng", theoretical_rate=coverage, construction_loss=loss,
            actual_rate_per_litter=per_litre, actual_rate_per_box=per_box, box_price=Decimal(box_price),
            color_mixing_price=color, unit_price_per_m2=D(Decimal(box_price) / per_box), percent_usage=share,
            area=area, total_price_area_based=D(boxes * box_price),
            litters=D(area * layers * share / per_litre), boxes=boxes,
            total_price_round=Decimal(boxes_round * box_price),
        )
        main_materials.append(row)
        tpab_sum += row["total_price_area_based"]
        tpr_sum += row["total_price_round"]
        color_total += color * boxes_round
        agg = boxes_by_product.setdefault(
            product_name, dict(boxes=Decimal(0), box_price=Decimal(box_price), package_type=row["package_type"])
        )
        agg["boxes"] += boxes

    # ---- quy trình thi công và nhân công ----
    if pin:
        step_names = list(pin.steps)
    else:
        pool = PROCESS_POOLS[PROCESS_KIND.get(entry.name, "paint")]
        step_names = [name for name in pool[:-2] if rng.random() < 0.7] + pool[-2:]
    steps = [] if stepless else [_step(name, main_materials, rng) for name in step_names]

    kn_rate, out_main_rate, out_sub_rate = ctx.rates
    processes = []
    for name in step_names:
        kn, out_main, out_sub = pin.workers if pin else _workers_for(ctx.profile, rng)
        intensity = pin.intensity if pin else rng.uniform(0.015, 0.04) * entry.labor_intensity
        intensity *= ctx.labor_factor
        days = max(Decimal("0.5"), D(area * Decimal(str(intensity)) / (kn + out_main + out_sub)))
        processes.append(dict(
            name=name, main_labors_kn=kn, main_labors_out=out_main, sub_labors_out=out_sub, days=days,
            kn_manday=D(kn * days), main_out_manday=D(out_main * days), sub_out_manday=D(out_sub * days),
        ))
    kn_md = sum((p["kn_manday"] for p in processes), Decimal(0))
    main_md = sum((p["main_out_manday"] for p in processes), Decimal(0))
    sub_md = sum((p["sub_out_manday"] for p in processes), Decimal(0))
    kn_total, main_total, sub_total = D(kn_md * kn_rate), D(main_md * out_main_rate), D(sub_md * out_sub_rate)
    kn_out_total = D(kn_md * out_main_rate)
    final_type = ctx.final_type or rng.choice(["has_kn", "all_out"])
    scenario_total = (kn_total if final_type == "has_kn" else kn_out_total) + main_total + sub_total
    labor_unit_price = D(scenario_total / area * ctx.coeff)

    # ---- đơn giá ----
    main_unit = D(tpab_sum / area)
    sub_unit = D(main_unit * Decimal(str(rng.uniform(0.05, 0.12))))
    noise = Decimal(1) if pin else Decimal(str(rng.uniform(0.98, 1.05)))
    material_unit = D((main_unit + sub_unit) * noise)
    margin = D(0.22 if pin else rng.uniform(0.15, 0.30), "0.0001")
    cost_unit = material_unit + labor_unit_price
    unit_price = D(cost_unit * (1 + margin))

    work_item = dict(
        key=key, name=entry.name, description=f"{entry.name}, thi công theo quy trình nhà sản xuất.",
        unit=entry.unit, quantity=area, unit_price=unit_price,
        concepts=[dict(type=t, name=n) for t, n in entry.tags], steps=steps,
    )
    estimation_item = dict(
        name=entry.name, work_item=key, main_unit_price=main_unit, sub_unit_price=sub_unit,
        material_unit_price=material_unit, total_price_area_based=tpab_sum, total_price_round=tpr_sum,
        material_unit_price_with_color_mixing_cost=D(material_unit + color_total / area),
        labor_unit_price=labor_unit_price, profit_margin=margin,
        labor=dict(
            area=area, kn_manday=kn_md, main_out_manday=main_md, sub_out_manday=sub_md,
            kn_total_price=kn_total, main_out_total_price=main_total, sub_out_total_price=sub_total,
            kn_out_total_price=kn_out_total, final_unit_price_type=final_type, labor_coeff=ctx.coeff,
            labor_unit_price=labor_unit_price, processes=processes,
        ),
        main_materials=main_materials,
    )
    sums = dict(
        material_round=tpr_sum, labor=scenario_total, profit=D(area * cost_unit * margin),
        quote=area * unit_price, boxes=boxes_by_product,
    )
    return work_item, estimation_item, sums


def _build_project(name: str, index: int, scenario: Scenario | None, base_name: str | None = None) -> dict:
    rng = random.Random(f"{SEED}:{name}")
    if scenario:
        project_name, street, place = f"{scenario.building} {scenario.base_name}", scenario.street, scenario.place
    else:
        project_name = f"{rng.choice(BUILDING_TYPES)} {base_name}"
        street, place = rng.choice(STREETS), rng.choice(PLACES)
    address = f"{rng.randint(1, 300)} {street}, {place}"
    issue = date(2025, 1, 1) + timedelta(days=rng.randint(0, 600))

    rates = scenario.rates if scenario and scenario.rates else (
        rng.randint(330, 420) * 1000, rng.randint(420, 560) * 1000, rng.randint(280, 380) * 1000
    )
    ctx = _ProjectContext(
        rates=tuple(Decimal(r) for r in rates),
        coeff=D(1.1 if scenario else rng.uniform(1.05, 1.25), "0.0001"),
        labor_factor=scenario.labor_factor if scenario else 1.0,
        profile=scenario.worker_profile if scenario else "standard",
        final_type=scenario.final_type if scenario else None,
    )
    has_estimation = scenario.has_estimation if scenario else True
    n_items = scenario.n_items if scenario else rng.randint(4, 8)
    pins = dict(scenario.pins) if scenario else {}

    chosen = [e for e in WORK_ITEM_CATALOG if e.name in pins]
    pool = [e for e in WORK_ITEM_CATALOG if e.name not in pins]
    chosen += rng.sample(pool, k=min(n_items - len(chosen), len(pool)))

    work_items, estimation_items, totals = [], [], dict(material_round=Decimal(0), labor=Decimal(0), profit=Decimal(0), quote=Decimal(0))
    product_boxes: dict[str, dict] = {}
    stepless_at = len(chosen) - 1 if scenario and scenario.stepless_item else None
    for i, entry in enumerate(chosen, start=1):
        work_item, est_item, sums = _build_item(
            rng, entry, i, ctx, pins.get(entry.name), stepless=(stepless_at == i - 1)
        )
        work_items.append(work_item)
        estimation_items.append(est_item)
        for k in totals:
            totals[k] += sums[k]
        for product, agg in sums["boxes"].items():
            slot = product_boxes.setdefault(product, dict(agg, boxes=Decimal(0)))
            slot["boxes"] += agg["boxes"]

    n_packages = 1 if len(work_items) < 5 else rng.choice([1, 2])
    packages = [dict(name=f"Gói thi công {p + 1}", work_items=[]) for p in range(n_packages)]
    for i, item in enumerate(work_items):
        packages[i % n_packages]["work_items"].append(item)

    quotation = dict(
        code=f"BG-{issue.year}-{index + 1:03d}", issue_date=issue, currency="VND",
        total_amount=D(totals["quote"]), packages=packages,
        scope_terms=[
            dict(scope_type=s, term_type=t, description=d) for s, t, d in rng.sample(SCOPE_ENTRIES, k=rng.randint(2, 4))
        ],
    )
    n_pay = rng.choice([2, 3, 4])
    weights = [rng.randint(10, 40) for _ in range(n_pay)]
    percentages = [D(w * 100 / sum(weights)) for w in weights]
    percentages[-1] += Decimal(100) - sum(percentages)
    quotation["payment_terms"] = [
        dict(percentage=pct, trigger_type=PAYMENT_TRIGGERS[n][0] if n < len(PAYMENT_TRIGGERS) else "OTHER",
             trigger_description=PAYMENT_TRIGGERS[n][1] if n < len(PAYMENT_TRIGGERS) else "Đợt thanh toán bổ sung")
        for n, pct in enumerate(percentages)
    ]
    has_warranty = rng.random() < 0.9
    if has_warranty:
        quotation["warranty"] = dict(
            period=rng.choice([12, 18, 24, 36]), period_unit="tháng",
            extend_percent=D(rng.choice([0, 5, 10])), extend_period=rng.choice([0, 3, 6]),
        )

    data = dict(
        project=dict(name=project_name, address=address,
                     estimated_workdays=[rng.randint(10, 60) for _ in range(rng.choice([1, 1, 2]))]),
        quotation=quotation,
    )

    has_extras = scenario.has_extras if scenario and scenario.has_extras is not None else rng.random() < 0.35
    if has_extras:
        amount = D(rng.randint(5, 50) * 1_000_000)
        data["extras"] = [dict(
            issue_date=issue + timedelta(days=rng.randint(10, 60)), total_amount=amount, currency="VND",
            description="Hạng mục phát sinh thêm theo yêu cầu chủ đầu tư", quantity=Decimal(1), unit="công trình",
            unit_price=amount,
        )]

    if has_estimation:
        sub_materials = []
        sub_total_sum = Decimal(0)
        for typ, sub_name, unit in rng.sample(SUB_MATERIAL_CATALOG, k=rng.randint(2, 4)):
            unit_price = D(rng.randint(20_000, 300_000))
            usages, sm_total = [], Decimal(0)
            for item in rng.sample(work_items, k=rng.randint(1, min(3, len(work_items)))):
                amount = D(rng.uniform(1, 20))
                usage_total = D(amount * unit_price)
                usages.append(dict(work_item=item["key"], amount=amount, total_price=usage_total))
                sm_total += usage_total
            sub_materials.append(dict(type=typ, name=sub_name, unit=unit, unit_price=unit_price,
                                      total_price=sm_total, usages=usages))
            sub_total_sum += sm_total

        material, labor = totals["material_round"], totals["labor"]
        details = [
            ("vật tư chính", "Vật tư chính", material),
            ("vật tư phụ", "Vật tư phụ / CCDC", sub_total_sum),
            ("nhân công", "Nhân công", labor),
            ("chi phí khác", "Giàn giáo & xử lý bề mặt", D((material + labor) * Decimal(str(rng.uniform(0.02, 0.06))))),
        ]
        if has_warranty:
            details.append(("chi phí bảo hành", "Chi phí bảo hành",
                            D((material + sub_total_sum + labor) * Decimal(str(rng.uniform(0.01, 0.02))))))
        details.append(("lợi nhuận thuần", "Lợi nhuận thuần", D(totals["profit"])))

        products = []
        for product, agg in product_boxes.items():
            boxes_round = max(1, math.ceil(agg["boxes"]))
            price = D(boxes_round * agg["box_price"])
            products.append(dict(
                product_name=product, package_type=agg["package_type"], boxes=D(agg["boxes"]), boxes_round=boxes_round,
                boxes_price=price, boxes_unit_price=agg["box_price"], total_price_round=price,
            ))
        data["estimation"] = dict(
            total_price=sum((price for _, _, price in details), Decimal(0)),
            total_details=[dict(type=t, name=n, price=p) for t, n, p in details],
            items=estimation_items, sub_materials=sub_materials, products_to_buy=products,
        )
    return data


def generate_all() -> list[tuple[str, dict]]:
    generated = [(f"{s.key}.yaml", _build_project(s.key, 100 + i, s)) for i, s in enumerate(SCENARIO_LIST)]
    scenario_base_names = {s.base_name for s in SCENARIO_LIST}
    free_names = [n for n in PROJECT_NAMES if n not in scenario_base_names]
    for i in range(RANDOM_PROJECT_COUNT):
        name = f"cong-trinh-{i + 1:02d}"
        generated.append((f"{name}.yaml", _build_project(name, i, None, base_name=free_names[i])))
    return sorted(generated)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/sample"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for stale in args.out.glob("*.yaml"):
        stale.unlink()
    for name, data in generate_all():
        (args.out / name).write_text(dump_yaml(data), encoding="utf-8")
    print(f"Đã ghi {len(list(args.out.glob('*.yaml')))} file vào {args.out}")


if __name__ == "__main__":
    main()
