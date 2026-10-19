import functools
import statistics
from decimal import Decimal
from pathlib import Path

import yaml

from app.domains.quotation.application.services.ingest.loader import load_quotation_text
from scripts.check_scrub import scan
from scripts.generate_sample_data import SCENARIOS, dump_yaml, generate_all

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"
WATERPROOF = "Chống thấm sân thượng"


@functools.cache
def _loaded() -> dict[str, "QuotationFile"]:  # noqa: F821 -- chỉ để gợi ý kiểu
    return {name: load_quotation_text(dump_yaml(data), name) for name, data in generate_all()}


def _item(file, name):
    for package in file.quotation.packages:
        for item in package.work_items:
            if item.name == name:
                return item
    raise AssertionError(f"{name} not found")


def _estimation_item(file, work_item_name):
    key = _item(file, work_item_name).key
    return next(e for e in file.estimation.items if e.work_item == key)


def test_generation_is_deterministic():
    assert generate_all() == generate_all()


def test_generates_between_20_and_30_projects_with_unique_names():
    generated = generate_all()

    names = [data["project"]["name"] for _, data in generated]
    assert 20 <= len(generated) <= 30
    assert len(set(names)) == len(names)


def test_every_generated_file_passes_loader():
    assert len(_loaded()) == len(generate_all())


def test_sample_directory_matches_generator():
    expected = {name: dump_yaml(data) for name, data in generate_all()}

    on_disk = {path.name: path.read_text(encoding="utf-8") for path in SAMPLE_DIR.glob("*.yaml")}

    assert on_disk == expected


def test_no_forbidden_words_in_sample_data():
    assert scan(SAMPLE_DIR) == []


def test_dump_round_trips_money_exactly():
    text = dump_yaml({"x": {"price": Decimal("1234567.89"), "qty": Decimal("500"), "rate": Decimal("0.2")}})

    assert "1234567.89" in text and "qty: 500\n" in text
    assert "!!" not in text


def test_material_scenario_gap_is_explained_by_material():
    files = _loaded()
    expensive, cheap = (files[f"{key}.yaml"] for key in ("bietthu-sen-vang", "bietthu-lua-non"))

    a, b = _estimation_item(expensive, WATERPROOF), _estimation_item(cheap, WATERPROOF)
    unit_a, unit_b = _item(expensive, WATERPROOF).unit_price, _item(cheap, WATERPROOF).unit_price

    assert unit_a >= unit_b * Decimal("1.25")
    material_gap = a.material_unit_price - b.material_unit_price
    labor_gap = abs(a.labor_unit_price - b.labor_unit_price)
    assert material_gap / (material_gap + labor_gap) >= Decimal("0.8")


def test_labor_scenario_gap_is_explained_by_outsourced_labor():
    files = _loaded()
    outsourced, inhouse = (files[f"{key}.yaml"] for key in ("nhapho-bach-duong", "nhapho-lien-hoa"))

    a, b = _estimation_item(outsourced, WATERPROOF), _estimation_item(inhouse, WATERPROOF)
    unit_a, unit_b = _item(outsourced, WATERPROOF).unit_price, _item(inhouse, WATERPROOF).unit_price

    assert unit_a >= unit_b * Decimal("1.25")
    labor_gap = a.labor_unit_price - b.labor_unit_price
    material_gap = abs(a.material_unit_price - b.material_unit_price)
    assert labor_gap / (labor_gap + material_gap) >= Decimal("0.8")
    assert a.labor.main_out_manday > 0 and (b.labor.main_out_manday or 0) == 0


def _labor_share(file) -> Decimal:
    labor = next(t.price for t in file.estimation.total_details if t.type == "nhân công")
    return labor / file.quotation.total_amount


def test_labor_heavy_project_is_an_outlier():
    files = _loaded()
    heavy = _labor_share(files["vanphong-ngoc-lan.yaml"])
    others = [_labor_share(f) for name, f in files.items() if f.estimation and name != "vanphong-ngoc-lan.yaml"]

    assert heavy >= Decimal(str(statistics.median(others))) * Decimal("1.5")


def test_scenario_without_estimation_has_no_estimation_block():
    files = _loaded()

    assert files["nhaxuong-thanh-cong.yaml"].estimation is None


def test_scenario_without_extras_and_with_stepless_item():
    school = _loaded()["truong-anh-sao.yaml"]

    assert school.extras == []
    assert any(item.steps == [] for package in school.quotation.packages for item in package.work_items)


def test_some_random_projects_have_extras_and_some_do_not():
    files = _loaded()
    flags = [bool(f.extras) for name, f in files.items() if name.startswith("cong-trinh-")]

    assert any(flags) and not all(flags)


def test_scenario_registry_lists_every_scenario_file():
    names = {name for name, _ in generate_all()}

    assert {f"{key}.yaml" for key in SCENARIOS} <= names
