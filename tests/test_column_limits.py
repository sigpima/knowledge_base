from app.domains.quotation.application.services.ingest.column_limits import SPEC_TO_MODEL


def test_every_mapped_column_exists_on_its_model():
    problems = []
    for spec, (model, overrides) in SPEC_TO_MODEL.items():
        columns = {column.name for column in model.__table__.columns}
        for field, column in {**{f: f for f in spec.model_fields}, **overrides}.items():
            if field in overrides and column not in columns:
                problems.append(f"{spec.__name__}.{field} -> {column}")
    assert problems == []


def test_every_scalar_spec_field_is_either_mapped_or_known_to_be_unstored():
    from app.domains.quotation.application.services.ingest.column_limits import UNSTORED_FIELDS

    unexplained = []
    for spec, (model, overrides) in SPEC_TO_MODEL.items():
        columns = {column.name for column in model.__table__.columns}
        for field in spec.model_fields:
            column = overrides.get(field, field)
            if column not in columns and (spec.__name__, field) not in UNSTORED_FIELDS:
                unexplained.append(f"{spec.__name__}.{field}")
    assert unexplained == []
