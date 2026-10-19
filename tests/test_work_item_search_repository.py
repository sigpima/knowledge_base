from decimal import Decimal

from app.domains.quotation.infrastructure.persistence.models import (
    ConceptModel,
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


def _concept(db_session, concept_type, name):
    concept = ConceptModel(type=concept_type, name=name)
    db_session.add(concept)
    db_session.flush()
    return concept


def _work_item(db_session, package_id, name, description, unit_price, concepts=None, sequence=1):
    item = WorkItemModel(
        package_id=package_id,
        sequence=sequence,
        name=name,
        description=description,
        quantity=Decimal("10"),
        unit="m2",
        unit_price=unit_price,
        total_price=unit_price * Decimal("10") if unit_price is not None else None,
        currency="VND",
        concepts=concepts or [],
    )
    db_session.add(item)
    db_session.commit()
    return item


def test_search_matches_name_case_insensitively(db_session):
    package_id = _seed_package(db_session)
    _work_item(db_session, package_id, "Sơn lót ngoại thất", None, Decimal("50000"))
    _work_item(db_session, package_id, "Chống thấm sân thượng", None, Decimal("70000"))

    repository = SqlAlchemyWorkItemRepository(db_session)
    results = repository.search(text="ngoại thất")

    assert len(results) == 1
    assert results[0]["name"] == "Sơn lót ngoại thất"


def test_search_filters_by_concept_type_and_name(db_session):
    package_id = _seed_package(db_session)
    application = _concept(db_session, "application", "Ngoại thất")
    _work_item(db_session, package_id, "Sơn lót A", None, Decimal("50000"), concepts=[application])
    _work_item(db_session, package_id, "Sơn lót B", None, Decimal("60000"))

    repository = SqlAlchemyWorkItemRepository(db_session)
    results = repository.search(concept_filters={"application": "Ngoại thất"})

    assert len(results) == 1
    assert results[0]["name"] == "Sơn lót A"


def test_search_with_no_filters_returns_up_to_limit(db_session):
    package_id = _seed_package(db_session)
    for i in range(3):
        _work_item(db_session, package_id, f"Hạng mục {i}", None, Decimal("1000"), sequence=i + 1)

    repository = SqlAlchemyWorkItemRepository(db_session)
    results = repository.search(limit=2)

    assert len(results) == 2


def test_search_returns_empty_list_when_nothing_matches(db_session):
    package_id = _seed_package(db_session)
    _work_item(db_session, package_id, "Sơn lót A", None, Decimal("50000"))

    repository = SqlAlchemyWorkItemRepository(db_session)
    assert repository.search(text="không tồn tại") == []


def test_count_matches_same_filters_as_search(db_session):
    package_id = _seed_package(db_session)
    application = _concept(db_session, "application", "Ngoại thất")
    _work_item(db_session, package_id, "Sơn lót A", None, Decimal("50000"), concepts=[application], sequence=1)
    _work_item(db_session, package_id, "Sơn lót B", None, Decimal("60000"), sequence=2)

    repository = SqlAlchemyWorkItemRepository(db_session)

    assert repository.count(text="Sơn lót") == 2
    assert repository.count(concept_filters={"application": "Ngoại thất"}) == 1
    assert repository.count(text="không tồn tại") == 0


def test_count_returns_true_total_even_when_search_is_limited(db_session):
    package_id = _seed_package(db_session)
    for i in range(5):
        _work_item(db_session, package_id, f"Hạng mục {i}", None, Decimal("1000"), sequence=i + 1)

    repository = SqlAlchemyWorkItemRepository(db_session)

    assert len(repository.search(limit=2)) == 2
    assert repository.count() == 5
