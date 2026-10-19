from decimal import Decimal

from app.domains.quotation.domain.entities import WorkItem
from app.domains.quotation.domain.value_objects.money import Money
from app.domains.quotation.domain.value_objects.quantity import Quantity
from app.domains.quotation.infrastructure.persistence.models import (
    ProjectModel,
    QuotationModel,
    QuotationPackageModel,
    WorkItemModel,
)
from app.domains.quotation.infrastructure.persistence.repositories.work_item_repository import (
    SqlAlchemyWorkItemRepository,
)


def _seed_package(db_session) -> int:
    project = ProjectModel(name="Test Project", address="Test Address")
    db_session.add(project)
    db_session.flush()

    quotation = QuotationModel(quotation_code="TEST-001", project_id=project.project_id, currency="VND")
    db_session.add(quotation)
    db_session.flush()

    package = QuotationPackageModel(quotation_id=quotation.quotation_id, name="Gói test", sequence=1)
    db_session.add(package)
    db_session.flush()
    return package.package_id


def test_save_then_get_by_id_round_trips_a_work_item(db_session):
    package_id = _seed_package(db_session)
    repository = SqlAlchemyWorkItemRepository(db_session)

    work_item = WorkItem(
        package_id=package_id,
        sequence=1,
        name="Sơn lót tường",
        description="Thi công sơn lót",
        quantity=Quantity(value=Decimal("10"), unit="m2"),
        unit_price=Money(amount=Decimal("50000"), currency="VND"),
    )

    saved = repository.save(work_item)
    assert saved.item_id is not None

    fetched = repository.get_by_id(saved.item_id)
    assert fetched.name == "Sơn lót tường"
    assert fetched.total_price == Money(Decimal("500000"), "VND")


def test_get_by_id_returns_none_for_missing_item(db_session):
    repository = SqlAlchemyWorkItemRepository(db_session)
    assert repository.get_by_id(999999) is None


def test_get_by_id_tolerates_null_quantity_unit_unit_price_from_real_ingest(db_session):
    package_id = _seed_package(db_session)
    model = WorkItemModel(
        package_id=package_id,
        sequence=1,
        name="Hạng mục chưa parse được",
        description=None,
        quantity=None,
        unit=None,
        unit_price=None,
        total_price=None,
        currency="VND",
    )
    db_session.add(model)
    db_session.commit()

    repository = SqlAlchemyWorkItemRepository(db_session)
    fetched = repository.get_by_id(model.item_id)

    assert fetched is not None
    assert fetched.quantity.value == Decimal("0")
    assert fetched.quantity.unit == "unknown"
    assert fetched.unit_price.amount == Decimal("0")


def test_delete_removes_the_row(db_session):
    package_id = _seed_package(db_session)
    repository = SqlAlchemyWorkItemRepository(db_session)
    saved = repository.save(WorkItem(
        package_id=package_id,
        sequence=1,
        name="Tạm",
        description="",
        quantity=Quantity(Decimal("1"), "m2"),
        unit_price=Money(Decimal("1000"), "VND"),
    ))

    repository.delete(saved.item_id)

    assert repository.get_by_id(saved.item_id) is None
