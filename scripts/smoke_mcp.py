"""Kiểm tra nhanh MCP server đang chạy (chỉ dùng thư viện chuẩn của Python).

    python3 -m scripts.smoke_mcp [URL]        # mặc định http://127.0.0.1:8002/mcp

Làm đúng chuỗi một agent làm: initialize -> tools/list -> gọi thử run_readonly_sql.
Thoát mã 0 nếu thấy đủ 11 tool và đếm được công trình trong DB.
"""
import sys

from scripts.mcp_client import DEFAULT_URL, McpError, McpSession

EXPECTED_TOOL_COUNT = 11


def main(url: str) -> int:
    session = McpSession(url)
    tools = [tool["name"] for tool in session.list_tools()]
    print(f"{len(tools)} tool: {', '.join(tools)}")
    if len(tools) != EXPECTED_TOOL_COUNT:
        print(f"Mong đợi {EXPECTED_TOOL_COUNT} tool", file=sys.stderr)
        return 1
    try:
        text = session.call_tool("run_readonly_sql", {"query": "SELECT count(*) AS projects FROM quotation.project"})
    except McpError as exc:
        print(f"run_readonly_sql lỗi: {exc}", file=sys.stderr)
        return 1
    print(f"run_readonly_sql -> {text}")
    return 0 if "projects" in text else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL))
