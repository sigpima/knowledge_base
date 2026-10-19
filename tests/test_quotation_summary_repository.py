from decimal import Decimal

from app.domains.quotation.infrastructure.persistence.models import (
    ProjectModel, QuotationModel, QuotationPackageModel, WorkItemModel,
)
from app.domains.quotation.infrastructure.persistence.repositories.quotation_repository import (
    SqlAlchemyQuotationRepository,
)


def _seed_quotation(db_session) -> QuotationModel:
    project = ProjectModel(name="Villa Test", address="123 Test St")
    db_session.add(project)
    db_session.flush()

    quotation = QuotationModel(quotation_code="Q-001", project_id=project.project_id, total_amount=Decimal("1000000"), currency="VND")
    db_session.add(quotation)
    db_session.flush()

    package = QuotationPackageModel(quotation_id=quotation.quotation_id, name="Gói I", sequence=1, total_amount=Decimal("1000000"))
    db_session.add(package)
    db_session.flush()

    work_item = WorkItemModel(package_id=package.package_id, sequence=1, name="Sơn tường", currency="VND", unit_price=Decimal("100000"), quantity=Decimal("10"), total_price=Decimal("1000000"))
    db_session.add(work_item)
    db_session.commit()
    return quotation


def test_summarize_quotation_without_version_loop(db_session):
    quotation = _seed_quotation(db_session)
    repo = SqlAlchemyQuotationRepository(db_session)

    summary = repo.summarize_quotation(quotation.quotation_id)

    assert summary["num_packages"] == 1
    assert summary["num_work_items"] == 1
    assert summary["total_amount"] == Decimal("1000000")


def test_summarize_project_without_version_loop(db_session):
    quotation = _seed_quotation(db_session)
    repo = SqlAlchemyQuotationRepository(db_session)

    summary = repo.summarize_project(quotation.project_id)

    assert summary["num_quotations"] == 1
    assert summary["num_packages"] == 1
    assert summary["total_amount"] == Decimal("1000000")
