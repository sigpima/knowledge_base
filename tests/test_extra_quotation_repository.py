from datetime import date
from decimal import Decimal

from app.domains.quotation.application.dto import CreateExtraQuotationData
from app.domains.quotation.infrastructure.persistence.models import ProjectModel
from app.domains.quotation.infrastructure.persistence.repositories.extra_quotation_repository import (
    SqlAlchemyExtraQuotationRepository,
)


def test_save_and_get_extra_quotation_roundtrip(db_session):
    project = ProjectModel(name="Villa Test", address="123 Test St")
    db_session.add(project)
    db_session.flush()

    repo = SqlAlchemyExtraQuotationRepository(db_session)
    saved = repo.save(
        project_id=project.project_id,
        data=CreateExtraQuotationData(
            issue_date=date(2026, 2, 1),
            total_amount=Decimal("5000000"),
            currency="VND",
            description="Sơn thêm ban công",
            quantity=Decimal("10"),
            unit="m2",
            unit_price=Decimal("500000"),
        ),
    )

    assert saved.extra_quotation_id is not None
    fetched = repo.get_by_id(saved.extra_quotation_id)
    assert fetched.total_amount == Decimal("5000000")
    assert fetched.description == "Sơn thêm ban công"


def test_get_by_id_returns_none_when_missing(db_session):
    repo = SqlAlchemyExtraQuotationRepository(db_session)
    assert repo.get_by_id(999999) is None
