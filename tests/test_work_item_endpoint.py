from decimal import Decimal

from fastapi.testclient import TestClient

from app.interfaces.http.api import app
from app.domains.quotation.infrastructure.persistence.models import (
    ProjectModel,
    QuotationModel,
    QuotationPackageModel,
    WorkItemModel,
)


def _seed_work_item(db_session) -> int:
    project = ProjectModel(name="Test Project", address="Test Address")
    db_session.add(project)
    db_session.flush()

    quotation = QuotationModel(quotation_code="TEST-001", project_id=project.project_id, currency="VND")
    db_session.add(quotation)
    db_session.flush()

    package = QuotationPackageModel(quotation_id=quotation.quotation_id, name="Gói test", sequence=1)
    db_session.add(package)
    db_session.flush()

    work_item = WorkItemModel(
        package_id=package.package_id,
        sequence=1,
        name="Sơn lót tường",
        description="Thi công sơn lót",
        quantity=Decimal("10"),
        unit="m2",
        unit_price=Decimal("50000"),
        total_price=Decimal("500000"),
        currency="VND",
    )
    db_session.add(work_item)
    db_session.commit()
    return work_item.item_id


def test_get_work_item_returns_404_for_missing_item(db_session):
    with TestClient(app) as client:
        response = client.get("/work-items/999999")
    assert response.status_code == 404


def test_get_work_item_returns_persisted_item(db_session):
    item_id = _seed_work_item(db_session)

    with TestClient(app) as client:
        response = client.get(f"/work-items/{item_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Sơn lót tường"
    assert body["total_price"] == 500000.0


def test_get_work_item_returns_503_when_service_uninitialized(monkeypatch):
    import app.interfaces.http.api as api_module

    with TestClient(app) as client:
        monkeypatch.setattr(api_module, "knowledge_service", None)
        response = client.get("/work-items/1")

    assert response.status_code == 503
