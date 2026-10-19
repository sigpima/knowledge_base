from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.services.knowledge_service import KnowledgeService
from app.domains.quotation.application.services.ingest.loader import load_quotation_file, load_quotation_text
from app.domains.quotation.application.services.ingest.writer import (
    DuplicateProjectError,
    IngestResult,
    ingest_quotation,
)
from app.domains.quotation.infrastructure.persistence import models as m
from app.domains.quotation.infrastructure.persistence.repositories.estimation_repository import (
    SqlAlchemyEstimationRepository,
)
from app.infrastructure.database.postgres.session import SessionLocal

FIXTURE = Path(__file__).parent / "fixtures" / "valid_minimal.yaml"

EXPECTED_ROWS = {
    m.ProjectModel: 1, m.QuotationModel: 1, m.QuotationPackageModel: 2, m.WorkItemModel: 3,
    m.WorkStepModel: 5, m.ConceptModel: 5, m.EstimationModel: 1, m.EstimationWorkItemModel: 2,
    m.LaborInfoModel: 2, m.LaborInfoProcessModel: 3, m.MainMaterialModel: 2, m.SubMaterialModel: 1,
    m.ItemSubModel: 1, m.ProductToBuyModel: 1, m.TotalDetailModel: 3, m.QuotationScopeTermModel: 2,
    m.QuotationPaymentTermModel: 2, m.QuotationWarrantyTermModel: 1, m.ExtraQuotationModel: 1,
}


def _count(session, model) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()


def test_ingest_full_file_writes_all_tables(db_session):
    result = ingest_quotation(db_session, load_quotation_file(FIXTURE), "hoa-sua.yaml")

    assert isinstance(result, IngestResult)
    assert (result.work_item_count, result.has_estimation, result.extra_count) == (3, True, 1)
    assert {model: _count(db_session, model) for model in EXPECTED_ROWS} == EXPECTED_ROWS
    project = db_session.get(m.ProjectModel, result.project_id)
    assert (project.name, project.source_file) == ("Biệt thự Hoa Sữa", "hoa-sua.yaml")


def test_estimation_items_link_to_the_right_work_items(db_session):
    ingest_quotation(db_session, load_quotation_file(FIXTURE), "x.yaml")

    rows = db_session.execute(
        select(m.EstimationWorkItemModel.name, m.WorkItemModel.name)
        .join(m.WorkItemModel, m.WorkItemModel.item_id == m.EstimationWorkItemModel.item_id)
        .order_by(m.EstimationWorkItemModel.cost_item_id)
    ).all()
    assert rows == [("Sơn nước ngoại thất", "Sơn nước ngoại thất"), ("Chống thấm sân thượng", "Chống thấm sân thượng")]
    usage = db_session.execute(select(m.ItemSubModel)).scalar_one()
    assert db_session.get(m.WorkItemModel, usage.item_id).name == "Sơn nước ngoại thất"


def test_ingest_without_estimation_or_extras(db_session):
    file = load_quotation_file(FIXTURE)
    file.estimation, file.extras = None, []

    result = ingest_quotation(db_session, file, "x.yaml")

    assert (result.has_estimation, result.extra_count) == (False, 0)
    assert _count(db_session, m.EstimationModel) == 0
    assert _count(db_session, m.ExtraQuotationModel) == 0
    assert _count(db_session, m.WorkItemModel) == 3


def test_work_item_without_steps(db_session):
    ingest_quotation(db_session, load_quotation_file(FIXTURE), "x.yaml")

    lonely = db_session.execute(select(m.WorkItemModel).where(m.WorkItemModel.name == "Sơn dầu lan can sắt")).scalar_one()
    assert db_session.execute(
        select(func.count()).select_from(m.WorkStepModel).where(m.WorkStepModel.item_id == lonely.item_id)
    ).scalar_one() == 0


def test_duplicate_project_name_raises_and_writes_nothing(db_session):
    file = load_quotation_file(FIXTURE)
    ingest_quotation(db_session, file, "a.yaml")

    with pytest.raises(DuplicateProjectError):
        ingest_quotation(db_session, file, "b.yaml")

    assert _count(db_session, m.ProjectModel) == 1
    assert _count(db_session, m.QuotationModel) == 1


def test_failure_in_estimation_rolls_back_quotation(db_session, monkeypatch):
    def boom(self, project_id, data):
        raise RuntimeError("estimation write failed")

    monkeypatch.setattr(SqlAlchemyEstimationRepository, "create", boom)

    with pytest.raises(RuntimeError):
        ingest_quotation(db_session, load_quotation_file(FIXTURE), "x.yaml")

    assert _count(db_session, m.ProjectModel) == 0
    assert _count(db_session, m.QuotationModel) == 0
    assert _count(db_session, m.WorkItemModel) == 0


def test_vietnamese_name_searchable_after_ingest(db_session):
    ingest_quotation(db_session, load_quotation_file(FIXTURE), "x.yaml")

    found = KnowledgeService(session_factory=SessionLocal).search_work_items(text="chống thấm")

    assert [item["name"] for item in found["items"]] == ["Chống thấm sân thượng"]


def test_money_round_trips_exactly_through_the_database(db_session):
    text = FIXTURE.read_text(encoding="utf-8").replace("unit_price: 95000", "unit_price: 1234567.89")
    text = text.replace("quantity: 40", "quantity: 0.1")

    ingest_quotation(db_session, load_quotation_text(text, "x.yaml"), "x.yaml")

    item = db_session.execute(select(m.WorkItemModel).where(m.WorkItemModel.name == "Sơn dầu lan can sắt")).scalar_one()
    assert (item.unit_price, item.quantity) == (Decimal("1234567.89"), Decimal("0.10"))


def test_nfd_search_text_still_finds_nfc_stored_names(db_session):
    import unicodedata

    ingest_quotation(db_session, load_quotation_file(FIXTURE), "x.yaml")
    typed_on_another_keyboard = unicodedata.normalize("NFD", "chống thấm")
    assert typed_on_another_keyboard != "chống thấm"

    found = KnowledgeService(session_factory=SessionLocal).search_work_items(text=typed_on_another_keyboard)
    by_concept = KnowledgeService(session_factory=SessionLocal).search_work_items(
        concept_filters={unicodedata.normalize("NFD", "effect"): unicodedata.normalize("NFD", "Chống thấm")}
    )

    assert [item["name"] for item in found["items"]] == ["Chống thấm sân thượng"]
    assert [item["name"] for item in by_concept["items"]] == ["Chống thấm sân thượng"]
