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
    assert result.status == "created"
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


def _variant(**changes) -> str:
    """Bản YAML của fixture với vài chỗ sửa (cùng tên công trình)."""
    text = FIXTURE.read_text(encoding="utf-8")
    for old, new in changes.items():
        assert old in text
        text = text.replace(old, new)
    return text


CHANGED = {"unit_price: 95000": "unit_price: 96000"}


def test_same_content_again_is_unchanged_and_writes_nothing(db_session):
    first = ingest_quotation(db_session, load_quotation_file(FIXTURE), "a.yaml")

    second = ingest_quotation(db_session, load_quotation_file(FIXTURE), "b.yaml")

    assert (first.status, second.status) == ("created", "unchanged")
    assert (second.project_id, second.quotation_id) == (first.project_id, first.quotation_id)
    assert (second.work_item_count, second.has_estimation, second.extra_count) == (3, True, 1)
    assert {model: _count(db_session, model) for model in EXPECTED_ROWS} == EXPECTED_ROWS
    assert db_session.get(m.ProjectModel, first.project_id).source_file == "a.yaml"


def test_hash_ignores_key_order_whitespace_and_trailing_zeros(db_session):
    import yaml

    ingest_quotation(db_session, load_quotation_file(FIXTURE), "a.yaml")
    reordered = yaml.safe_dump(yaml.safe_load(FIXTURE.read_text(encoding="utf-8")), allow_unicode=True, sort_keys=True)
    padded = _variant(**{"unit_price: 95000": "unit_price: 95000.00", "quantity: 500": "quantity: 500.000"})

    for text in (reordered, padded):
        result = ingest_quotation(db_session, load_quotation_text(text, "t.yaml"), "b.yaml")
        assert result.status == "unchanged"
    assert _count(db_session, m.ProjectModel) == 1


def test_same_name_different_content_raises_and_writes_nothing(db_session):
    ingest_quotation(db_session, load_quotation_file(FIXTURE), "a.yaml")

    with pytest.raises(DuplicateProjectError, match="replace"):
        ingest_quotation(db_session, load_quotation_text(_variant(**CHANGED), "t.yaml"), "b.yaml")

    assert {model: _count(db_session, model) for model in EXPECTED_ROWS} == EXPECTED_ROWS
    price = db_session.execute(select(m.WorkItemModel.unit_price).where(m.WorkItemModel.name == "Sơn dầu lan can sắt")).scalar_one()
    assert price == Decimal("95000")


def test_replace_swaps_the_whole_tree_in_one_transaction(db_session):
    first = ingest_quotation(db_session, load_quotation_file(FIXTURE), "a.yaml")
    changed = load_quotation_text(_variant(**CHANGED), "t.yaml")
    changed.estimation, changed.extras = None, []

    result = ingest_quotation(db_session, changed, "b.yaml", on_conflict="replace")

    assert result.status == "replaced" and result.project_id != first.project_id
    assert (result.has_estimation, result.extra_count) == (False, 0)
    assert _count(db_session, m.ProjectModel) == 1
    for model in (m.QuotationModel, m.QuotationPackageModel, m.WorkItemModel, m.WorkStepModel, m.QuotationScopeTermModel,
                  m.QuotationPaymentTermModel, m.QuotationWarrantyTermModel):
        assert _count(db_session, model) == EXPECTED_ROWS[model], model.__name__
    for model in (m.EstimationModel, m.EstimationWorkItemModel, m.LaborInfoModel, m.LaborInfoProcessModel,
                  m.MainMaterialModel, m.SubMaterialModel, m.ItemSubModel, m.ProductToBuyModel, m.TotalDetailModel,
                  m.ExtraQuotationModel):
        assert _count(db_session, model) == 0, model.__name__
    assert db_session.get(m.ProjectModel, result.project_id).source_file == "b.yaml"


def test_replace_with_same_content_is_still_unchanged(db_session):
    first = ingest_quotation(db_session, load_quotation_file(FIXTURE), "a.yaml")

    second = ingest_quotation(db_session, load_quotation_file(FIXTURE), "a.yaml", on_conflict="replace")

    assert (second.status, second.project_id) == ("unchanged", first.project_id)


def test_failed_replace_keeps_the_old_data(db_session, monkeypatch):
    first = ingest_quotation(db_session, load_quotation_file(FIXTURE), "a.yaml")

    def boom(self, project_id, data):
        raise RuntimeError("estimation write failed")

    monkeypatch.setattr(SqlAlchemyEstimationRepository, "create", boom)
    with pytest.raises(RuntimeError):
        ingest_quotation(db_session, load_quotation_text(_variant(**CHANGED), "t.yaml"), "b.yaml", on_conflict="replace")

    assert {model: _count(db_session, model) for model in EXPECTED_ROWS} == EXPECTED_ROWS
    assert db_session.get(m.ProjectModel, first.project_id).source_file == "a.yaml"


def _simulate_lost_race(monkeypatch):
    """Lần kiểm tra 'đã có chưa' đầu tiên thấy rỗng (như khi một request khác vừa ghi xen vào)."""
    from app.domains.quotation.application.services.ingest import writer

    real = writer._find_project
    calls = []

    def racing(session, name):
        calls.append(name)
        return None if len(calls) == 1 else real(session, name)

    monkeypatch.setattr(writer, "_find_project", racing)


def test_lost_race_with_identical_content_resolves_to_unchanged(db_session, monkeypatch):
    first = ingest_quotation(db_session, load_quotation_file(FIXTURE), "a.yaml")
    _simulate_lost_race(monkeypatch)

    second = ingest_quotation(db_session, load_quotation_file(FIXTURE), "b.yaml")

    assert (second.status, second.project_id) == ("unchanged", first.project_id)
    assert _count(db_session, m.ProjectModel) == 1


def test_lost_race_with_different_content_raises_duplicate(db_session, monkeypatch):
    ingest_quotation(db_session, load_quotation_file(FIXTURE), "a.yaml")
    _simulate_lost_race(monkeypatch)

    with pytest.raises(DuplicateProjectError):
        ingest_quotation(db_session, load_quotation_text(_variant(**CHANGED), "t.yaml"), "b.yaml")

    assert {model: _count(db_session, model) for model in EXPECTED_ROWS} == EXPECTED_ROWS


def test_database_itself_rejects_two_projects_with_the_same_name(db_session):
    from sqlalchemy.exc import IntegrityError

    db_session.add_all([m.ProjectModel(name="Trùng tên", address="a"), m.ProjectModel(name="Trùng tên", address="b")])

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


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
