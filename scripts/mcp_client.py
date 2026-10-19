"""Client MCP tối giản qua HTTP (chỉ dùng thư viện chuẩn), dùng cho smoke test và gọi thử tool."""
import json
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8002/mcp"


class McpError(RuntimeError):
    pass


def _post(url: str, payload: dict, session_id: str | None = None) -> tuple[str | None, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.headers.get("Mcp-Session-Id"), response.read().decode("utf-8")


def parse_response(body: str) -> dict:
    """Phản hồi có thể là JSON thuần hoặc SSE (`data: {...}`)."""
    body = body.strip()
    if body.startswith("{"):
        return json.loads(body)
    for line in body.splitlines():
        if line.startswith("data:"):
            return json.loads(line[len("data:"):].strip())
    raise McpError(f"Không đọc được phản hồi MCP: {body[:200]!r}")


def tool_text(result: dict) -> str:
    text = "".join(part.get("text", "") for part in result.get("content", []))
    if result.get("isError"):
        raise McpError(text or "tool báo lỗi")
    return text


class McpSession:
    def __init__(self, url: str = DEFAULT_URL):
        self.url = url
        self._next_id = 0
        self.session_id, body = _post(url, self._request("initialize", {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "knowledge-base-client", "version": "1.0"},
        }))
        parse_response(body)
        _post(url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, self.session_id)

    def _request(self, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            payload["params"] = params
        return payload

    def _call(self, method: str, params: dict | None = None) -> dict:
        _, body = _post(self.url, self._request(method, params), self.session_id)
        message = parse_response(body)
        if "error" in message:
            raise McpError(str(message["error"]))
        return message["result"]

    def list_tools(self) -> list[dict]:
        return self._call("tools/list")["tools"]

    def call_tool(self, name: str, arguments: dict | None = None) -> str:
        return tool_text(self._call("tools/call", {"name": name, "arguments": arguments or {}}))
