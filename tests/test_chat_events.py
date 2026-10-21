"""Kiểm thử mô hình sự kiện và tóm tắt kết quả tool của chat streaming."""
import json

from mcp.types import CallToolResult, TextContent

from app.chat.events import ChatEvent, summarize_tool_result


def _result(payload, is_error: bool = False) -> CallToolResult:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return CallToolResult(content=[TextContent(type="text", text=text)], is_error=is_error)


def test_to_sse_format():
    assert ChatEvent("answer", {"text": "Xin chào"}).to_sse() == 'event: answer\ndata: {"text": "Xin chào"}\n\n'


def test_row_count_from_run_readonly_sql():
    result = _result({"rows": [{"a": 1}, {"a": 2}], "row_count": 2, "truncated": False})
    summary = summarize_tool_result("run_readonly_sql", {"query": "SELECT a FROM t"}, result)
    assert summary["ok"] is True
    assert summary["row_count"] == 2
    assert summary["sql"] == "SELECT a FROM t"


def test_row_count_none_for_structured_tools_without_rows():
    summary = summarize_tool_result("get_project", {"name": "X"}, _result({"name": "X", "total": 10}))
    assert summary["ok"] is True
    assert summary["row_count"] is None
    assert summary["sql"] is None


def test_row_count_from_rows_or_items_length():
    assert summarize_tool_result("t", {}, _result({"items": [1, 2, 3]}))["row_count"] == 3
    assert summarize_tool_result("t", {}, _result({"rows": [1]}))["row_count"] == 1


def test_structured_content_is_read_first():
    result = CallToolResult(
        content=[TextContent(type="text", text="không phải JSON")],
        structured_content={"rows": [1, 2], "row_count": 2},
    )
    assert summarize_tool_result("run_readonly_sql", {"query": "q"}, result)["row_count"] == 2


def test_error_result_is_not_ok():
    assert summarize_tool_result("t", {}, _result("boom", is_error=True))["ok"] is False
    assert summarize_tool_result("run_readonly_sql", {"query": "q"}, _result({"error": "sai"}))["ok"] is False


def test_non_json_text_is_used_verbatim():
    summary = summarize_tool_result("t", {}, _result("văn bản thường"))
    assert summary["preview"] == "văn bản thường"
    assert summary["row_count"] is None


def test_preview_is_truncated_to_800_chars():
    summary = summarize_tool_result("t", {}, _result("x" * 5000))
    assert len(summary["preview"]) == 800
