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
