import pytest

from app.mcp.sql_guard import validate_select_only, ensure_limit


def test_validate_select_only_accepts_a_plain_select():
    validate_select_only("SELECT * FROM quotation.work_item")


def test_validate_select_only_accepts_lowercase_select():
    validate_select_only("select item_id from quotation.work_item")


def test_validate_select_only_rejects_insert():
    with pytest.raises(ValueError):
        validate_select_only("INSERT INTO quotation.work_item (name) VALUES ('x')")


def test_validate_select_only_rejects_multiple_statements():
    with pytest.raises(ValueError):
        validate_select_only("SELECT 1; DROP TABLE quotation.work_item")


def test_validate_select_only_rejects_empty_query():
    with pytest.raises(ValueError):
        validate_select_only("   ")


def test_ensure_limit_appends_limit_when_missing():
    result = ensure_limit("SELECT * FROM quotation.work_item")
    assert result == "SELECT * FROM quotation.work_item LIMIT 200"


def test_ensure_limit_strips_trailing_semicolon_before_appending():
    result = ensure_limit("SELECT * FROM quotation.work_item;")
    assert result == "SELECT * FROM quotation.work_item LIMIT 200"


def test_ensure_limit_leaves_existing_limit_untouched():
    result = ensure_limit("SELECT * FROM quotation.work_item LIMIT 10")
    assert result == "SELECT * FROM quotation.work_item LIMIT 10"


def test_ensure_limit_respects_custom_default():
    result = ensure_limit("SELECT * FROM quotation.work_item", default_limit=5)
    assert result == "SELECT * FROM quotation.work_item LIMIT 5"
