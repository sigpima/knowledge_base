"""Kiểm tra nhanh MCP server đang chạy (chỉ dùng thư viện chuẩn của Python).

    python3 scripts/smoke_mcp.py [URL]        # mặc định http://127.0.0.1:8002/mcp

Thực hiện đúng chuỗi mà một agent làm: initialize -> tools/list -> gọi thử run_readonly_sql.
Thoát mã 0 nếu thấy đủ 10 tool và đếm được công trình trong DB.
"""
import json
import sys
import urllib.request

EXPECTED_TOOL_COUNT = 10


def _post(url: str, payload: dict, session_id: str | None = None):
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
        return response.headers.get("Mcp-Session-Id"), body


def _parse(body: str) -> dict:
    """Phản hồi có thể là JSON thuần hoặc SSE (`data: {...}`)."""
    body = body.strip()
    if body.startswith("{"):
        return json.loads(body)
    for line in body.splitlines():
        if line.startswith("data:"):
            return json.loads(line[len("data:"):].strip())
    raise ValueError(f"Không đọc được phản hồi MCP: {body[:200]!r}")


def main(url: str) -> int:
    session_id, body = _post(url, {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                   "clientInfo": {"name": "smoke-mcp", "version": "1.0"}},
    })
    _parse(body)
    _post(url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id)

    _, body = _post(url, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, session_id)
    tools = [tool["name"] for tool in _parse(body)["result"]["tools"]]
    print(f"{len(tools)} tool: {', '.join(tools)}")
    if len(tools) != EXPECTED_TOOL_COUNT:
        print(f"Mong đợi {EXPECTED_TOOL_COUNT} tool", file=sys.stderr)
        return 1

    _, body = _post(url, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "run_readonly_sql",
                   "arguments": {"query": "SELECT count(*) AS projects FROM quotation.project"}},
    }, session_id)
    result = _parse(body)["result"]
    text = "".join(part.get("text", "") for part in result.get("content", []))
    print(f"run_readonly_sql -> {text}")
    return 0 if "projects" in text and not result.get("isError") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8002/mcp"))
