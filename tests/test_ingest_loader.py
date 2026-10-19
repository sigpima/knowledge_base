import unicodedata
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from app.domains.quotation.application.services.ingest.loader import (
    QuotationFileError,
    load_quotation_file,
    load_quotation_text,
)

FIXTURE = Path(__file__).parent / "fixtures" / "valid_minimal.yaml"


def _mutated(mutate) -> str:
    data = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    mutate(data)
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def _errors(text: str) -> list[str]:
    with pytest.raises(QuotationFileError) as info:
        load_quotation_text(text, "test.yaml")
    return info.value.errors


def test_valid_minimal_loads():
    loaded = load_quotation_file(FIXTURE)

    assert loaded.project.name == "Biệt thự Hoa Sữa"
    assert [len(p.work_items) for p in loaded.quotation.packages] == [2, 1]
    assert loaded.estimation is not None and len(loaded.estimation.items) == 2


def test_money_keeps_exact_decimal():
    text = FIXTURE.read_text(encoding="utf-8").replace("unit_price: 95000", "unit_price: 1234567.89")
    text = text.replace("quantity: 40", "quantity: 0.1")

    item = load_quotation_text(text, "t.yaml").quotation.packages[1].work_items[0]

    assert item.unit_price == Decimal("1234567.89")
    assert item.quantity == Decimal("0.1")


def test_duplicate_work_item_key_rejected():
    def mutate(d):
        d["quotation"]["packages"][0]["work_items"][1]["key"] = "ngoai-that-tuong"

    errors = _errors(_mutated(mutate))

    assert any(e.startswith("quotation.packages[0].work_items[1].key") for e in errors)


def test_dangling_work_item_reference_rejected():
    def mutate(d):
        d["estimation"]["items"][0]["work_item"] = "khong-ton-tai"

    errors = _errors(_mutated(mutate))

    assert any(e.startswith("estimation.items[0].work_item") and "khong-ton-tai" in e for e in errors)


def test_dangling_sub_material_usage_rejected():
    def mutate(d):
        d["estimation"]["sub_materials"][0]["usages"][0]["work_item"] = "nope"

    assert any(e.startswith("estimation.sub_materials[0].usages[0].work_item") for e in _errors(_mutated(mutate)))


def test_unknown_concept_rejected():
    def mutate(d):
        d["quotation"]["packages"][0]["work_items"][0]["concepts"][0]["name"] = "Sao Hỏa"

    errors = _errors(_mutated(mutate))

    assert any(e.startswith("quotation.packages[0].work_items[0].concepts[0]") for e in errors)


def test_total_amount_mismatch_rejected():
    def mutate(d):
        d["quotation"]["total_amount"] = 1

    assert any(e.startswith("quotation.total_amount") for e in _errors(_mutated(mutate)))


def test_total_amount_filled_when_missing():
    loaded = load_quotation_file(FIXTURE)

    assert loaded.quotation.total_amount == Decimal("72800000")


def test_total_amount_accepted_when_it_matches():
    def mutate(d):
        d["quotation"]["total_amount"] = 72800000

    assert load_quotation_text(_mutated(mutate), "t.yaml").quotation.total_amount == Decimal("72800000")


def test_cost_relation_outside_tolerance_rejected():
    def mutate(d):
        d["estimation"]["items"][0]["profit_margin"] = 0.5

    errors = _errors(_mutated(mutate))

    assert any(e.startswith("estimation.items[0]") and "profit_margin" in e for e in errors)


def test_python_object_tag_rejected():
    errors = _errors("project: !!python/object/apply:os.system ['echo hi']\n")

    assert errors


def test_yaml_alias_rejected():
    text = "a: &x [1, 2, 3]\nb: *x\n"

    assert any("alias" in e.lower() for e in _errors(text))


def test_unknown_field_rejected_with_path():
    def mutate(d):
        d["project"]["colour"] = "red"

    assert any(e.startswith("project.colour") for e in _errors(_mutated(mutate)))


def test_bom_and_nfd_text_normalized():
    nfd_name = unicodedata.normalize("NFD", "Chống thấm sân thượng")
    text = "﻿" + FIXTURE.read_text(encoding="utf-8").replace("Chống thấm sân thượng", nfd_name)

    loaded = load_quotation_text(text, "t.yaml")

    assert loaded.quotation.packages[0].work_items[1].name == "Chống thấm sân thượng"
    assert unicodedata.is_normalized("NFC", loaded.quotation.packages[0].work_items[1].name)


def test_warranty_requires_every_field_the_database_requires():
    def mutate(d):
        del d["quotation"]["warranty"]["extend_period"]

    assert any(e.startswith("quotation.warranty.extend_period") for e in _errors(_mutated(mutate)))


def test_payment_term_requires_percentage_and_trigger():
    def mutate(d):
        del d["quotation"]["payment_terms"][0]["percentage"]

    assert any(e.startswith("quotation.payment_terms[0].percentage") for e in _errors(_mutated(mutate)))


def test_term_type_longer_than_column_rejected():
    def mutate(d):
        d["quotation"]["scope_terms"][0]["term_type"] = "X" * 11

    assert any(e.startswith("quotation.scope_terms[0].term_type") for e in _errors(_mutated(mutate)))


def test_deeply_nested_yaml_is_rejected_not_crashed():
    errors = _errors("a: " + "[" * 20000 + "]" * 20000 + "\n")

    assert errors


# ---- giới hạn cột DB: lỗi 422 có vị trí thay vì 500 hoặc làm tròn âm thầm ----

WORK_ITEM = "quotation.packages[0].work_items[0]"


def test_unit_longer_than_column_rejected():
    def mutate(d):
        d["quotation"]["packages"][0]["work_items"][0]["unit"] = "m" * 21

    assert any(e.startswith(f"{WORK_ITEM}.unit") for e in _errors(_mutated(mutate)))


def test_name_longer_than_255_rejected():
    def mutate(d):
        d["project"]["name"] = "x" * 256

    assert any(e.startswith("project.name") for e in _errors(_mutated(mutate)))


def test_percent_usage_written_as_percentage_rejected():
    def mutate(d):
        d["estimation"]["items"][0]["main_materials"][0]["percent_usage"] = 100

    assert any(e.startswith("estimation.items[0].main_materials[0].percent_usage") for e in _errors(_mutated(mutate)))


def test_more_decimal_places_than_column_would_store_rejected():
    text = FIXTURE.read_text(encoding="utf-8").replace("unit_price: 95000", "unit_price: 95000.123")

    assert any(e.startswith("quotation.packages[1].work_items[0].unit_price") for e in _errors(text))


def test_trailing_zero_decimals_are_still_fine():
    text = FIXTURE.read_text(encoding="utf-8").replace("unit_price: 95000", "unit_price: 95000.100")

    assert load_quotation_text(text, "t.yaml").quotation.packages[1].work_items[0].unit_price == Decimal("95000.1")


def test_integer_overflowing_column_rejected():
    def mutate(d):
        d["quotation"]["packages"][0]["work_items"][0]["steps"][1]["layers"] = 99999999999

    assert any("steps[1].layers" in e for e in _errors(_mutated(mutate)))


def test_duplicate_concept_on_one_item_rejected():
    def mutate(d):
        concepts = d["quotation"]["packages"][0]["work_items"][0]["concepts"]
        concepts.append(dict(concepts[0]))

    assert any(e.startswith(f"{WORK_ITEM}.concepts[2]") and "trùng" in e for e in _errors(_mutated(mutate)))


def test_two_estimation_items_for_one_work_item_rejected():
    def mutate(d):
        d["estimation"]["items"][1]["work_item"] = d["estimation"]["items"][0]["work_item"]

    assert any(e.startswith("estimation.items[1].work_item") and "trùng" in e for e in _errors(_mutated(mutate)))


def test_gigantic_integer_rejected_not_crashed():
    assert _errors("a: " + "9" * 5000 + "\n")


def test_decimal_with_gigantic_exponent_rejected_not_crashed():
    text = FIXTURE.read_text(encoding="utf-8").replace("unit_price: 95000", "unit_price: 1.0e+999999999")

    assert any("unit_price" in e for e in _errors(text))


def test_extras_metadata_must_be_json_safe():
    def mutate(d):
        d["extras"][0]["metadata"] = {"rate": 0.5}

    assert any(e.startswith("extras[0].metadata") for e in _errors(_mutated(mutate)))


def test_extras_metadata_with_plain_values_is_accepted():
    def mutate(d):
        d["extras"][0]["metadata"] = {"ghi_chu": "theo yêu cầu", "so_luong": 3, "da_duyet": True}

    assert load_quotation_text(_mutated(mutate), "t.yaml").extras[0].metadata["so_luong"] == 3


def test_duplicate_mapping_key_rejected():
    text = FIXTURE.read_text(encoding="utf-8").replace(
        "          unit_price: 95000\n", "          unit_price: 95000\n          unit_price: 1\n"
    )

    assert any("unit_price" in e and "lặp" in e for e in _errors(text))
