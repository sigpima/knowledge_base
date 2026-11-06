"""Kiểm thử mô hình sự kiện và tóm tắt kết quả tool của chat streaming."""
import json

from mcp.types import CallToolResult, TextContent

from app.chat.events import POLICY_TOOL, PREVIEW_MAX_CHARS, ChatEvent, summarize_tool_result


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


def test_structured_content_wrapped_in_result_key_is_unwrapped():
    wrapped = CallToolResult(
        content=[TextContent(type="text", text="{}")],
        structured_content={"result": {"rows": [{"n": 1}], "row_count": 1, "truncated": False}},
        is_error=False,
    )
    assert summarize_tool_result("run_readonly_sql", {"query": "q"}, wrapped)["row_count"] == 1

    failed = CallToolResult(
        content=[TextContent(type="text", text="{}")],
        structured_content={"result": {"error": "boom"}},
        is_error=False,
    )
    assert summarize_tool_result("run_readonly_sql", {"query": "q"}, failed)["ok"] is False


def _passage(slug: str, section: str, score, text: str = "Nội dung rất dài của đoạn chính sách."):
    return {"slug": slug, "title": "Tiêu đề", "doc_type": "technical", "section": section, "text": text, "score": score}


def test_policy_preview_is_one_citation_line_per_passage_without_text():
    payload = {
        "passages": [_passage("quy-trinh-son", "Chuẩn bị bề mặt", 0.8765), _passage("bao-hanh", "Thời hạn > Nội thất", 0.5)],
        "row_count": 2,
    }
    summary = summarize_tool_result(POLICY_TOOL, {"query": "câu hỏi riêng tư"}, _result(payload))
    assert POLICY_TOOL == "search_policies"
    assert summary["ok"] is True
    assert summary["row_count"] == 2
    assert summary["sql"] is None
    assert summary["preview"] == "quy-trinh-son › Chuẩn bị bề mặt · 0.88\nbao-hanh › Thời hạn > Nội thất · 0.50"
    assert "Nội dung rất dài" not in summary["preview"]
    assert "riêng tư" not in json.dumps(summary, ensure_ascii=False)


def test_policy_preview_is_cut_to_the_limit():
    payload = {"passages": [_passage(f"slug-{i}", "m" * 100, 0.9) for i in range(30)], "row_count": 30}
    summary = summarize_tool_result(POLICY_TOOL, {"query": "q"}, _result(payload))
    assert len(summary["preview"]) == PREVIEW_MAX_CHARS
    assert summary["row_count"] == 30


def test_policy_empty_result_has_zero_rows_and_empty_preview():
    summary = summarize_tool_result(POLICY_TOOL, {"query": "q"}, _result({"passages": [], "row_count": 0}))
    assert summary["ok"] is True
    assert summary["row_count"] == 0
    assert summary["preview"] == ""


def test_policy_error_is_not_ok_and_previews_the_message():
    summary = summarize_tool_result(POLICY_TOOL, {"query": "q"}, _result({"error": "Kho chính sách chưa được nạp."}))
    assert summary["ok"] is False
    assert summary["row_count"] is None
    assert summary["sql"] is None
    assert summary["preview"] == "Kho chính sách chưa được nạp."

    long_error = summarize_tool_result(POLICY_TOOL, {"query": "q"}, _result({"error": "e" * 5000}))
    assert len(long_error["preview"]) == PREVIEW_MAX_CHARS


def test_policy_malformed_payloads_fall_back_to_generic_summary():
    for payload in ({"passages": "không phải list"}, {"row_count": 1}, ["a", "b"], "văn bản thường",
                    {"passages": [None, "x", {"slug": "chỉ-slug"}], "row_count": 3}):
        summary = summarize_tool_result(POLICY_TOOL, {"query": "q"}, _result(payload))
        assert summary["sql"] is None
        assert isinstance(summary["preview"], str)
        assert len(summary["preview"]) <= PREVIEW_MAX_CHARS
