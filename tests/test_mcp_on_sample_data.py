import asyncio
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

import main_mcp
from app.infrastructure.database.postgres.session import SessionLocal, engine
from scripts.seed import seed

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"
WATERPROOF = "Chống thấm sân thượng"
EXPECTED_TOOLS = {
    "get_quotation", "find_quotations", "get_work_item", "search_work_items", "compare_work_item_price",
    "compare_work_item_detail", "get_project_overview", "compare_labor_cost",
    "compare_project_cost_breakdown", "run_readonly_sql",
}


@pytest.fixture(scope="module")
def seeded(db_engine):
    results = seed(SessionLocal, SAMPLE_DIR)
    yield results
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE quotation.project RESTART IDENTITY CASCADE"))


def _scalar(sql: str, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


def _project_id(name: str) -> int:
    return _scalar("SELECT project_id FROM quotation.project WHERE name = :n", n=name)


def _item_id(project_name: str, item_name: str) -> int:
    return _scalar(
        "SELECT w.item_id FROM quotation.work_item w "
        "JOIN quotation.package p ON p.package_id = w.package_id "
        "JOIN quotation.quotation q ON q.quotation_id = p.quotation_id "
        "JOIN quotation.project pr ON pr.project_id = q.project_id "
        "WHERE pr.name = :p AND w.name = :i", p=project_name, i=item_name,
    )


def test_server_registers_exactly_ten_tools():
    tools = asyncio.run(main_mcp.mcp.list_tools())

    assert {tool.name for tool in tools} == EXPECTED_TOOLS and len(tools) == 10


def test_get_project_overview_handles_project_without_estimation(seeded):
    overview = main_mcp.get_project_overview(_project_id("Nhà xưởng Thành Công"))

    assert overview["project_name"] == "Nhà xưởng Thành Công"
    assert overview["estimation"] is None
    assert overview["quotation_summary"]["total_amount"] is not None


def test_get_project_overview_includes_cost_breakdown_when_estimation_exists(seeded):
    overview = main_mcp.get_project_overview(_project_id("Biệt thự Sen Vàng"))

    assert overview["estimation"]["cost_breakdown"]["by_type"]


def test_tools_return_none_when_there_is_no_estimation(seeded):
    project_id = _project_id("Nhà xưởng Thành Công")
    item_id = _scalar(
        "SELECT w.item_id FROM quotation.work_item w JOIN quotation.package p ON p.package_id = w.package_id "
        "JOIN quotation.quotation q ON q.quotation_id = p.quotation_id WHERE q.project_id = :p LIMIT 1",
        p=project_id,
    )
    other_item = _item_id("Biệt thự Sen Vàng", WATERPROOF)

    assert main_mcp.get_work_item(item_id)["estimation"] is None
    assert main_mcp.compare_project_cost_breakdown(project_id, "labor") is None
    assert main_mcp.compare_labor_cost(project_id) is None
    assert main_mcp.compare_work_item_detail(item_id, other_item) is None


def test_unknown_ids_return_none(seeded):
    assert main_mcp.get_project_overview(999_999) is None
    assert main_mcp.get_quotation(999_999) is None
    assert main_mcp.get_work_item(999_999) is None


def test_find_quotations_returns_highest_total_first_with_work_items(seeded):
    result = main_mcp.find_quotations(order_by="total_amount_desc", limit=1)

    assert result["matched_count"] == len(seeded)
    top = result["quotations"][0]
    assert Decimal(top["total_amount"]) == _scalar("SELECT max(total_amount) FROM quotation.quotation")
    assert top["packages"][0]["work_items"]


def test_find_quotations_caps_limit_and_rejects_unknown_order(seeded):
    assert len(main_mcp.find_quotations(limit=10)["quotations"]) == 3
    assert "error" in main_mcp.find_quotations(order_by="nonsense")


def test_search_work_items_by_text_and_concept(seeded):
    by_text = main_mcp.search_work_items(text="chống thấm", limit=5)
    by_concept = main_mcp.search_work_items(concept_filters={"effect": "Chống thấm"}, limit=5)

    assert by_text["matched_count"] > 0 and by_concept["matched_count"] > 0
    assert all("chống thấm" in item["name"].lower() for item in by_text["items"])


def test_compare_work_item_price_finds_other_waterproofing_items(seeded):
    result = main_mcp.compare_work_item_price(_item_id("Biệt thự Sen Vàng", WATERPROOF))

    assert result["matched_count"] >= 3
    assert any(m["name"] == WATERPROOF for m in result["matched_items"])
    assert Decimal(result["pct_diff_from_avg"]) > 0


def _gap_share(result: dict, main_key: str, other_key: str) -> Decimal:
    main_gap = abs(Decimal(result[main_key]))
    return main_gap / (main_gap + abs(Decimal(result[other_key])))


def test_compare_work_item_detail_explains_material_scenario(seeded):
    result = main_mcp.compare_work_item_detail(
        _item_id("Biệt thự Sen Vàng", WATERPROOF), _item_id("Biệt thự Lúa Non", WATERPROOF)
    )

    # Các trường *_diff của tool được tính là B trừ A, nên A đắt hơn B thì diff âm.
    assert Decimal(result["price_diff"]) < 0
    assert _gap_share(result, "material_unit_price_diff", "labor_unit_price_diff") >= Decimal("0.8")


def test_compare_work_item_detail_explains_labor_scenario(seeded):
    result = main_mcp.compare_work_item_detail(
        _item_id("Nhà phố Bạch Dương", WATERPROOF), _item_id("Nhà phố Liên Hoa", WATERPROOF)
    )

    assert Decimal(result["price_diff"]) < 0
    assert _gap_share(result, "labor_unit_price_diff", "material_unit_price_diff") >= Decimal("0.8")
    assert Decimal(result["labor_info_diff"]["main_out_manday_diff"]) < 0


def test_compare_project_cost_breakdown_flags_labor_heavy_project(seeded):
    result = main_mcp.compare_project_cost_breakdown(_project_id("Văn phòng Ngọc Lan"), "labor")

    assert result["matched_count"] >= 10
    assert Decimal(result["pct_point_diff_from_avg"]) > 10


def test_compare_labor_cost_returns_similar_projects(seeded):
    outsourced = main_mcp.compare_labor_cost(_project_id("Nhà phố Bạch Dương"))
    inhouse = main_mcp.compare_labor_cost(_project_id("Nhà phố Liên Hoa"))

    assert outsourced["matched_count"] >= 1 and outsourced["matched_projects"]
    assert Decimal(outsourced["total_out_cost"]) > Decimal(inhouse["total_out_cost"])


def test_run_readonly_sql_selects_and_rejects_writes(seeded):
    counted = main_mcp.run_readonly_sql("SELECT count(*) AS n FROM quotation.project")
    rejected = main_mcp.run_readonly_sql("DELETE FROM quotation.project")

    assert counted["rows"] == [{"n": len(seeded)}]
    assert "error" in rejected
    assert _scalar("SELECT count(*) FROM quotation.project") == len(seeded)
