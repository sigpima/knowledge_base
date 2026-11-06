"""Sự kiện của chat streaming (SSE) và tóm tắt kết quả tool để gửi cho client."""
import json
from dataclasses import dataclass
from typing import Any

PREVIEW_MAX_CHARS = 800
SQL_TOOL = "run_readonly_sql"
POLICY_TOOL = "search_policies"


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
        # Quan sát được: qua MCP server thật + SDK, structured_content đến dưới dạng `{"result": {...}}`, kể cả với tool
        # khai báo kiểu trả về `Dict`. Bóc lớp bọc đó để `row_count` và `error` nằm ở tầng ngoài.
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


def _policy_preview(payload) -> tuple[str, int] | None:
    """Mỗi đoạn một dòng `<slug> › <section> · <score>` (không kèm nguyên văn đoạn) và số đoạn; payload lạ thì None."""
    if not isinstance(payload, dict):
        return None
    passages = payload.get("passages")
    if not isinstance(passages, list):
        return None
    lines = []
    for passage in passages:
        if not isinstance(passage, dict):
            return None
        slug, section, score = passage.get("slug"), passage.get("section"), passage.get("score")
        if not isinstance(slug, str) or not isinstance(section, str):
            return None
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            return None
        lines.append(f"{slug} › {section} · {score:.2f}")
    return "\n".join(lines), len(lines)


def summarize_tool_result(tool: str, args: dict, result) -> dict:
    """Rút gọn `mcp.types.CallToolResult` thành `{ok, row_count, sql, preview}`."""
    payload = _result_payload(result)
    ok = not getattr(result, "is_error", False) and not (isinstance(payload, dict) and "error" in payload)
    text = _result_text(result)
    if text is None:
        text = "" if payload is None else json.dumps(payload, ensure_ascii=False, default=str)
    row_count = _row_count(payload)
    if tool == POLICY_TOOL and isinstance(payload, dict):
        if "error" in payload:
            text = str(payload["error"])
        elif (policy := _policy_preview(payload)) is not None:
            text, row_count = policy
    return {
        "ok": ok,
        "row_count": row_count,
        "sql": args.get("query") if tool == SQL_TOOL else None,
        "preview": text[:PREVIEW_MAX_CHARS],
    }
