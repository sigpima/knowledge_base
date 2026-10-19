import pytest

from app.mcp.sql_guard import ensure_limit, validate_select_only


def test_validate_select_only_accepts_a_plain_select():
    validate_select_only("SELECT * FROM quotation.work_item")


def test_validate_select_only_accepts_lowercase_select():
    validate_select_only("select item_id from quotation.work_item")


def test_validate_select_only_accepts_with_queries():
    validate_select_only("WITH t AS (SELECT 1 AS a) SELECT * FROM t")


def test_validate_select_only_accepts_semicolon_and_keywords_inside_string_literals():
    validate_select_only("SELECT 'a;b' AS x, 'drop table' AS y, \"delete\" FROM (SELECT 1 AS \"delete\") s")


def test_validate_select_only_accepts_a_leading_comment():
    validate_select_only("-- đếm công trình\nSELECT count(*) FROM quotation.project")


def test_validate_select_only_accepts_dollar_quoted_text():
    validate_select_only("SELECT $$a;b$$ AS x")


@pytest.mark.parametrize("query", [
    "INSERT INTO quotation.work_item (name) VALUES ('x')",
    "SELECT 1; DROP TABLE quotation.work_item",
    "SELECT ';' ; DROP TABLE quotation.work_item",
    "WITH d AS (DELETE FROM quotation.work_item RETURNING *) SELECT * FROM d",
    "SELECT 1 /* ok */; UPDATE quotation.project SET name = 'x'",
    "   ",
    "-- chỉ có chú thích",
])
def test_validate_select_only_rejects(query):
    with pytest.raises(ValueError):
        validate_select_only(query)


def test_ensure_limit_wraps_the_query_in_an_outer_limit():
    assert ensure_limit("SELECT * FROM quotation.work_item") == (
        "SELECT * FROM (\nSELECT * FROM quotation.work_item\n) AS limited_query LIMIT 200"
    )


def test_ensure_limit_strips_trailing_semicolon():
    assert "work_item;" not in ensure_limit("SELECT * FROM quotation.work_item;")


def test_ensure_limit_still_applies_when_the_query_has_its_own_limit_or_the_word_in_a_literal():
    for query in ("SELECT * FROM quotation.work_item LIMIT 10", "SELECT 'limit' AS word, g FROM generate_series(1, 9) g"):
        assert ensure_limit(query).endswith(") AS limited_query LIMIT 200"), query


def test_ensure_limit_survives_a_trailing_line_comment():
    assert ensure_limit("SELECT 1 -- hết").endswith("\n) AS limited_query LIMIT 200")


def test_ensure_limit_respects_custom_default():
    assert ensure_limit("SELECT 1", default_limit=5).endswith("LIMIT 5")
