from sqlalchemy import inspect


def test_version_and_product_tables_removed(db_engine):
    inspector = inspect(db_engine)
    tables = inspector.get_table_names(schema="quotation")
    assert "version" not in tables
    assert "product" not in tables


def test_extra_quotation_table_exists(db_engine):
    inspector = inspect(db_engine)
    tables = inspector.get_table_names(schema="quotation")
    assert "extra_quotation" in tables


def test_quotation_table_has_fields_moved_from_version(db_engine):
    inspector = inspect(db_engine)
    columns = {c["name"] for c in inspector.get_columns("quotation", schema="quotation")}
    assert {"issue_date", "total_amount", "currency", "metadata"} <= columns


def test_project_has_estimated_workdays_array(db_engine):
    inspector = inspect(db_engine)
    columns = {c["name"]: c for c in inspector.get_columns("project", schema="quotation")}
    assert "estimated_workdays" in columns
    assert "source_file" in columns
    assert "created_at" in columns


def test_work_step_has_product_name_string(db_engine):
    inspector = inspect(db_engine)
    columns = {c["name"] for c in inspector.get_columns("work_step", schema="quotation")}
    assert "product_name" in columns
    assert "product_id" not in columns


def test_package_and_terms_fk_quotation_directly(db_engine):
    inspector = inspect(db_engine)
    for table in ("package", "scope_term", "warranty_term", "payment_term"):
        columns = {c["name"] for c in inspector.get_columns(table, schema="quotation")}
        assert "quotation_id" in columns
        assert "quotation_version_id" not in columns
