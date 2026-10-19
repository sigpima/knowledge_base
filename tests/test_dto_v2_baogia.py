# tests/test_dto_v2_baogia.py
from datetime import date
from decimal import Decimal

from app.domains.quotation.application.dto import (
    CreateProjectData,
    CreateQuotationData,
    CreateWorkStepData,
    CreateExtraQuotationData,
    QuotationKnowledge,
)


def test_create_project_data_has_estimated_workdays_and_source_file():
    project = CreateProjectData(
        name="Villa Test",
        address="123 Test St",
        source_file="03.21.pdf",
        estimated_workdays=[30, 6],
    )
    assert project.source_file == "03.21.pdf"
    assert project.estimated_workdays == [30, 6]


def test_create_quotation_data_carries_former_version_fields():
    quotation = CreateQuotationData(
        quotation_code="Q-001",
        issue_date=date(2026, 1, 1),
        total_amount=Decimal("548363247.96"),
        currency="VND",
        metadata={"vat_rate": 0.1},
    )
    assert quotation.total_amount == Decimal("548363247.96")
    assert quotation.packages == []


def test_create_work_step_data_uses_product_name_string():
    step = CreateWorkStepData(sequence=1, name="Sơn lót", product_name="VIETCOAT SEAL-11A")
    assert step.product_name == "VIETCOAT SEAL-11A"
    assert not hasattr(step, "product")


def test_quotation_knowledge_has_no_version_field():
    knowledge = QuotationKnowledge(
        quotation=CreateQuotationData(quotation_code="Q-001"),
        project=CreateProjectData(name="Villa Test", address="123 Test St"),
    )
    assert not hasattr(knowledge, "version")


def test_create_extra_quotation_data_roundtrip():
    extra = CreateExtraQuotationData(
        issue_date=date(2026, 2, 1),
        total_amount=Decimal("5000000"),
        currency="VND",
        description="Sơn thêm ban công",
        quantity=Decimal("10"),
        unit="m2",
        unit_price=Decimal("500000"),
    )
    assert extra.total_amount == Decimal("5000000")
