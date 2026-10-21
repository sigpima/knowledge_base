"""Sự kiện của chat streaming (SSE) và tóm tắt kết quả tool để gửi cho client."""
import json
from dataclasses import dataclass
from typing import Any

PREVIEW_MAX_CHARS = 800
SQL_TOOL = "run_readonly_sql"


@dataclass(frozen=True)
class ChatEvent:
    """Một sự kiện SSE: `start`, `tool_call`, `tool_result`, `answer`, `error` hoặc `done`."""

    type: str
    data: dict

    def to_sse(self) -> str:
        return f"event: {self.type}\ndata: {json.dumps(self.data, ensure_ascii=False)}\n\n"


def _result_text(result) -> str | None:
    """Văn bản của khối nội dung đầu tiên, nếu có."""
    content = getattr(result, "content", None) or []
    return getattr(content[0], "text", None) if content else None


def _result_payload(result) -> Any:
    """Ưu tiên structured_content; không có thì parse JSON từ văn bản; không parse được thì giữ nguyên văn."""
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        # FastMCP bọc kết quả của tool có kiểu trả về là union (vd `Dict | None`) thành `{"result": ...}`; bóc lớp bọc đó
        # để `row_count` và `error` nằm ở tầng ngoài như khi tool trả về dict thường.
        if isinstance(structured, dict) and set(structured) == {"result"}:
            return structured["result"]
        return structured
    text = _result_text(result)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text


def _row_count(payload) -> int | None:
    if not isinstance(payload, dict):
        return None
    count = payload.get("row_count")
    if isinstance(count, int) and not isinstance(count, bool):
        return count
    for key in ("rows", "items"):
        if isinstance(payload.get(key), list):
            return len(payload[key])
    return None


def summarize_tool_result(tool: str, args: dict, result) -> dict:
    """Rút gọn `mcp.types.CallToolResult` thành `{ok, row_count, sql, preview}`."""
    payload = _result_payload(result)
    ok = not getattr(result, "is_error", False) and not (isinstance(payload, dict) and "error" in payload)
    text = _result_text(result)
    if text is None:
        text = "" if payload is None else json.dumps(payload, ensure_ascii=False, default=str)
    return {
        "ok": ok,
        "row_count": _row_count(payload),
        "sql": args.get("query") if tool == SQL_TOOL else None,
        "preview": text[:PREVIEW_MAX_CHARS],
    }
