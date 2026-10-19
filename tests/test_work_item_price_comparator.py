from decimal import Decimal

from app.domains.quotation.application.dto import CreateConceptData, CreateWorkItemData
from app.domains.quotation.infrastructure.persistence.models import (
    ConceptModel,
    ProjectModel,
    QuotationModel,
    QuotationPackageModel,
    WorkItemModel,
)
from app.domains.quotation.application.services.work_item_service import (
    WorkItemApplicationService,
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


def _seed_work_item(db_session, package_id, name, unit_price, concept_pairs, sequence=1, unit="m2"):
    concepts = []
    for concept_type, concept_name in concept_pairs:
        concept = (
            db_session.query(ConceptModel)
            .filter(ConceptModel.type == concept_type, ConceptModel.name == concept_name)
            .one_or_none()
        )
        if concept is None:
            concept = ConceptModel(type=concept_type, name=concept_name)
            db_session.add(concept)
            db_session.flush()
        concepts.append(concept)

    work_item = WorkItemModel(
        package_id=package_id,
        sequence=sequence,
        name=name,
        description=None,
        quantity=Decimal("10"),
        unit=unit,
        unit_price=unit_price,
        total_price=(unit_price * Decimal("10")) if unit_price is not None else None,
        currency="VND",
        concepts=concepts,
    )
    db_session.add(work_item)
    db_session.commit()
    return work_item


def _new_item(name, unit_price, concept_pairs, unit="m2"):
    return CreateWorkItemData(
        name=name,
        description=None,
        unit=unit,
        unit_price=unit_price,
        quantity=Decimal("10"),
        currency="VND",
        concepts=[CreateConceptData(type=t, name=n) for t, n in concept_pairs],
    )


def test_matches_by_category_application_object_and_computes_stats(db_session):
    package_id = _seed_package(db_session)
    concept_pairs = [
        ("category", "Sơn trang trí"),
        ("application", "Ngoại thất"),
        ("object", "Tường"),
    ]
    _seed_work_item(db_session, package_id, "1.1 Sơn lót chống kiềm tường ngoài", Decimal("40000"), concept_pairs)
    _seed_work_item(db_session, package_id, "1.2 Sơn phủ hoàn thiện tường ngoài", Decimal("52000"), concept_pairs, sequence=2)

    comparator = WorkItemApplicationService(session=db_session)
    new_item = _new_item("1.1 Sơn lót chống kiềm tường ngoài", Decimal("45000"), concept_pairs)

    result = comparator.compare_price(new_item)

    assert result.matched_count == 2
    assert result.historical_min == Decimal("40000")
    assert result.historical_max == Decimal("52000")
    assert result.historical_avg == Decimal("46000")
    assert result.pct_diff_from_avg == float(round((Decimal("45000") - Decimal("46000")) / Decimal("46000") * 100, 1))


def test_returns_zero_matched_when_new_item_has_no_category(db_session):
    package_id = _seed_package(db_session)
    _seed_work_item(
        db_session, package_id, "1.1 Sơn lót chống kiềm tường ngoài", Decimal("40000"),
        [("category", "Sơn trang trí"), ("application", "Ngoại thất"), ("object", "Tường")],
    )

    comparator = WorkItemApplicationService(session=db_session)
    new_item = _new_item("Hạng mục lạ", Decimal("10000"), [])

    result = comparator.compare_price(new_item)

    assert result.matched_count == 0
    assert result.historical_min is None
    assert result.historical_max is None
    assert result.historical_avg is None
    assert result.pct_diff_from_avg is None


def test_returns_zero_matched_when_no_historical_category_matches(db_session):
    package_id = _seed_package(db_session)
    _seed_work_item(
        db_session, package_id, "Chống thấm sân thượng", Decimal("70000"),
        [("category", "Chống thấm"), ("application", "Ngoại thất"), ("object", "Sân thượng")],
    )

    comparator = WorkItemApplicationService(session=db_session)
    new_item = _new_item(
        "Sơn phủ hoàn thiện", Decimal("45000"),
        [("category", "Sơn trang trí"), ("application", "Ngoại thất"), ("object", "Tường")],
    )

    result = comparator.compare_price(new_item)

    assert result.matched_count == 0


def test_falls_back_to_full_concept_group_when_no_name_clears_threshold(db_session):
    package_id = _seed_package(db_session)
    concept_pairs = [("category", "Sơn trang trí"), ("object", "Tường")]
    _seed_work_item(db_session, package_id, "Hoàn toàn khác tên", Decimal("30000"), concept_pairs)

    comparator = WorkItemApplicationService(session=db_session)
    new_item = _new_item("1.1 Sơn lót chống kiềm tường ngoài", Decimal("45000"), concept_pairs)

    result = comparator.compare_price(new_item)

    assert result.matched_count == 1
    assert result.historical_avg == Decimal("30000")


def test_excludes_historical_rows_with_null_unit_price(db_session):
    package_id = _seed_package(db_session)
    concept_pairs = [("category", "Sơn trang trí"), ("object", "Tường")]
    _seed_work_item(db_session, package_id, "1.1 Sơn lót chống kiềm tường ngoài", None, concept_pairs)
    _seed_work_item(db_session, package_id, "1.2 Sơn lót chống kiềm tường ngoài", Decimal("40000"), concept_pairs, sequence=2)

    comparator = WorkItemApplicationService(session=db_session)
    new_item = _new_item("1.1 Sơn lót chống kiềm tường ngoài", Decimal("45000"), concept_pairs)

    result = comparator.compare_price(new_item)

    assert result.matched_count == 1
    assert result.historical_avg == Decimal("40000")


def test_excludes_historical_rows_with_mismatched_unit(db_session):
    package_id = _seed_package(db_session)
    concept_pairs = [
        ("category", "Sơn trang trí"),
        ("application", "Ngoại thất"),
        ("object", "Tường"),
    ]
    # Historical row priced as a lump-sum package ("Gói"), not a per-m2 rate --
    # must not be averaged in with an m2-unit new item even though concepts match.
    _seed_work_item(
        db_session, package_id, "1.1 Sơn lót chống kiềm tường ngoài", Decimal("5000000"), concept_pairs, unit="Gói"
    )

    comparator = WorkItemApplicationService(session=db_session)
    new_item = _new_item("1.1 Sơn lót chống kiềm tường ngoài", Decimal("45000"), concept_pairs, unit="m2")

    result = comparator.compare_price(new_item)

    assert result.matched_count == 0
    assert result.historical_min is None
    assert result.historical_max is None
    assert result.historical_avg is None
    assert result.pct_diff_from_avg is None


def test_compare_by_item_id_matches_against_other_persisted_items(db_session):
    package_id = _seed_package(db_session)
    historical = _seed_work_item(
        db_session, package_id, "Sơn lót ngoại thất cũ", Decimal("100000"),
        [("category", "Sơn trang trí"), ("application", "Ngoại thất")],
    )
    target = _seed_work_item(
        db_session, package_id, "Sơn lót ngoại thất mới", Decimal("120000"),
        [("category", "Sơn trang trí"), ("application", "Ngoại thất")], sequence=2,
    )

    comparator = WorkItemApplicationService(session=db_session)
    result = comparator.compare_price_by_item_id(target.item_id)

    assert result is not None
    assert result.matched_count == 1
    assert result.historical_avg == Decimal("100000")


def test_compare_by_item_id_returns_none_for_missing_item(db_session):
    comparator = WorkItemApplicationService(session=db_session)
    assert comparator.compare_price_by_item_id(999999) is None


def test_returns_zero_matched_when_new_item_has_no_unit(db_session):
    package_id = _seed_package(db_session)
    concept_pairs = [
        ("category", "Sơn trang trí"),
        ("application", "Ngoại thất"),
        ("object", "Tường"),
    ]
    _seed_work_item(db_session, package_id, "1.1 Sơn lót chống kiềm tường ngoài", Decimal("40000"), concept_pairs)

    comparator = WorkItemApplicationService(session=db_session)
    new_item = _new_item("1.1 Sơn lót chống kiềm tường ngoài", Decimal("45000"), concept_pairs, unit=None)

    result = comparator.compare_price(new_item)

    assert result.matched_count == 0
    assert result.historical_min is None
    assert result.historical_max is None
    assert result.historical_avg is None
    assert result.pct_diff_from_avg is None


def test_matched_items_include_name_project_name_unit_price_ordered_by_similarity(db_session):
    package_id = _seed_package(db_session)
    concept_pairs = [
        ("category", "Sơn trang trí"),
        ("application", "Ngoại thất"),
        ("object", "Tường"),
    ]
    exact_match = _seed_work_item(
        db_session, package_id, "1.1 Sơn lót chống kiềm tường ngoài", Decimal("40000"), concept_pairs
    )
    _seed_work_item(
        db_session, package_id, "1.2 Sơn phủ hoàn thiện tường ngoài", Decimal("52000"), concept_pairs, sequence=2
    )

    comparator = WorkItemApplicationService(session=db_session)
    new_item = _new_item("1.1 Sơn lót chống kiềm tường ngoài", Decimal("45000"), concept_pairs)

    result = comparator.compare_price(new_item)

    assert len(result.matched_items) == 2
    assert result.matched_items[0].item_id == exact_match.item_id
    assert result.matched_items[0].name == "1.1 Sơn lót chống kiềm tường ngoài"
    assert result.matched_items[0].project_name == "Test Project"
    assert result.matched_items[0].unit_price == Decimal("40000")
    assert result.matched_items[0].name_similarity_score == 1.0
    assert result.matched_items[1].name == "1.2 Sơn phủ hoàn thiện tường ngoài"
    assert result.matched_items[1].name_similarity_score < result.matched_items[0].name_similarity_score


def test_matched_items_capped_at_ten_while_matched_count_stays_true_total(db_session):
    package_id = _seed_package(db_session)
    concept_pairs = [("category", "Sơn trang trí"), ("object", "Tường")]
    for i in range(11):
        _seed_work_item(
            db_session, package_id, f"Sơn lót tường {i}", Decimal("40000"), concept_pairs, sequence=i + 1
        )

    comparator = WorkItemApplicationService(session=db_session)
    new_item = _new_item("Sơn lót tường 0", Decimal("41000"), concept_pairs)

    result = comparator.compare_price(new_item)

    assert result.matched_count == 11
    assert len(result.matched_items) == 10
