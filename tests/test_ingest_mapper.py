from decimal import Decimal
from pathlib import Path

from app.domains.quotation.application.dto import (
    CreateEstimationBundleData,
    CreateExtraQuotationData,
    QuotationKnowledge,
)
from app.domains.quotation.application.services.ingest.loader import load_quotation_file
from app.domains.quotation.application.services.ingest.mapper import (
    TermsData,
    WorkItemSlot,
    to_estimation_bundle,
    to_extra_quotations,
    to_knowledge,
    to_terms,
)

FIXTURE = Path(__file__).parent / "fixtures" / "valid_minimal.yaml"


def _file():
    return load_quotation_file(FIXTURE)


def test_to_knowledge_preserves_package_and_item_order():
    knowledge, slots = to_knowledge(_file(), source_file="hoa-sua.yaml")

    assert isinstance(knowledge, QuotationKnowledge)
    assert knowledge.project.name == "Biệt thự Hoa Sữa"
    assert knowledge.project.source_file == "hoa-sua.yaml"
    assert knowledge.project.estimated_workdays == [30, 6]
    packages = knowledge.quotation.packages
    assert [p.name for p in packages] == ["Gói sơn ngoại thất", "Gói hạng mục phụ"]
    assert [len(p.work_items) for p in packages] == [2, 1]
    assert slots == {
        "ngoai-that-tuong": WorkItemSlot(0, 0),
        "chong-tham-san-thuong": WorkItemSlot(0, 1),
        "son-lan-can": WorkItemSlot(1, 0),
    }


def test_to_knowledge_copies_quotation_fields_and_work_item_values():
    knowledge, _ = to_knowledge(_file(), source_file="x.yaml")

    quotation = knowledge.quotation
    assert quotation.quotation_code == "BG-2026-001"
    assert quotation.total_amount == Decimal("72800000")
    item = quotation.packages[0].work_items[0]
    assert (item.name, item.unit, item.quantity, item.unit_price, item.currency) == (
        "Sơn nước ngoại thất", "m2", Decimal("500"), Decimal("102000"), "VND",
    )
    assert [(c.type, c.name) for c in item.concepts] == [("category", "Ngoại thất"), ("application", "Tường")]


def test_work_steps_sequence_starts_at_one():
    knowledge, _ = to_knowledge(_file(), source_file="x.yaml")

    steps = knowledge.quotation.packages[0].work_items[0].work_steps
    assert [s.sequence for s in steps] == [1, 2, 3]
    assert steps[2].product_name == "Vietcoat Top-2" and steps[2].layers == 2


def test_work_item_without_steps_has_empty_step_list():
    knowledge, _ = to_knowledge(_file(), source_file="x.yaml")

    assert knowledge.quotation.packages[1].work_items[0].work_steps == []


def test_estimation_item_gets_item_id_from_key():
    bundle = to_estimation_bundle(_file(), {"ngoai-that-tuong": 11, "chong-tham-san-thuong": 12, "son-lan-can": 13})

    assert isinstance(bundle, CreateEstimationBundleData)
    items = bundle.estimation.estimation_work_items
    assert [(i.name, i.item_id) for i in items] == [("Sơn nước ngoại thất", 11), ("Chống thấm sân thượng", 12)]
    assert items[0].labor_info.kn_manday == Decimal("20")
    assert [p.name for p in items[0].labor_info.processes] == ["Vệ sinh bề mặt", "Sơn phủ"]
    assert items[0].main_materials[0].product_name == "Vietcoat Top-2"
    assert [(t.type, t.price) for t in bundle.estimation.total_details][0] == ("vật tư chính", Decimal("40000000"))
    assert bundle.estimation.total_price == Decimal("79500000")


def test_item_sub_usage_uses_item_id():
    bundle = to_estimation_bundle(_file(), {"ngoai-that-tuong": 11, "chong-tham-san-thuong": 12, "son-lan-can": 13})

    usage = bundle.sub_materials[0].usages[0]
    assert (usage.item_id, usage.amount, usage.total_price) == (11, Decimal("20"), Decimal("300000"))
    assert bundle.products_to_buy[0].product_name == "Vietcoat Top-2"


def test_estimation_none_when_file_has_no_estimation():
    file = _file()
    file.estimation = None

    assert to_estimation_bundle(file, {}) is None


def test_extras_mapped():
    extras = to_extra_quotations(_file())

    assert extras == [
        CreateExtraQuotationData(
            issue_date=extras[0].issue_date,
            total_amount=Decimal("1800000"),
            currency="VND",
            description="Xử lý nứt chân tường phát sinh",
            quantity=Decimal("12"),
            unit="m",
            unit_price=Decimal("150000"),
            metadata={},
        )
    ]
    assert str(extras[0].issue_date) == "2026-04-02"


def test_terms_mapped():
    terms = to_terms(_file())

    assert isinstance(terms, TermsData)
    assert [(t.scope_type, t.term_type) for t in terms.scope] == [("bao gồm", "INCLUDE"), ("loại trừ", "EXCLUDE")]
    assert [(t.sequence, t.percentage, t.trigger_type) for t in terms.payment] == [
        (1, Decimal("30"), "DEPOSIT"), (2, Decimal("70"), "FINAL"),
    ]
    assert (terms.warranty.period, terms.warranty.period_unit) == (24, "tháng")


def test_terms_empty_when_file_has_none():
    file = _file()
    file.quotation.scope_terms, file.quotation.payment_terms, file.quotation.warranty = [], [], None

    terms = to_terms(file)

    assert (terms.scope, terms.payment, terms.warranty) == ([], [], None)
