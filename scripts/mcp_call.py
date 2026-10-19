"""Gọi thử một tool MCP từ terminal, không cần agent.

    python3 -m scripts.mcp_call list
    python3 -m scripts.mcp_call find_quotations '{"order_by": "total_amount_desc", "limit": 1}'
    python3 -m scripts.mcp_call run_readonly_sql '{"query": "SELECT name FROM quotation.project LIMIT 3"}'

Đặt MCP_URL để trỏ tới server khác (mặc định http://127.0.0.1:8002/mcp). Đặt MCP_CALL_LOG=đường/dẫn.jsonl để ghi
lại từng lần gọi (tool, tham số, kết quả) làm bằng chứng cho transcript.
"""
import json
import os
import sys

from scripts.mcp_client import DEFAULT_URL, McpSession


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    session = McpSession(os.environ.get("MCP_URL", DEFAULT_URL))
    if argv[0] == "list":
        for tool in session.list_tools():
            print(f"## {tool['name']}\n{tool.get('description', '')}\n")
        return 0

    arguments = json.loads(argv[1]) if len(argv) > 1 else {}
    result = session.call_tool(argv[0], arguments)
    print(result)
    log_path = os.environ.get("MCP_CALL_LOG")
    if log_path:
        with open(log_path, "a", encoding="utf-8") as log:
            log.write(json.dumps({"tool": argv[0], "arguments": arguments, "result": result}, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
