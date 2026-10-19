import json

import pytest

from scripts.mcp_client import McpError, parse_response, tool_text


def test_parse_response_reads_plain_json():
    assert parse_response('{"jsonrpc": "2.0", "id": 1, "result": {"ok": true}}')["result"] == {"ok": True}


def test_parse_response_reads_server_sent_event_body():
    body = 'event: message\ndata: {"jsonrpc": "2.0", "id": 2, "result": {"tools": []}}\n\n'

    assert parse_response(body)["result"] == {"tools": []}


def test_parse_response_rejects_unreadable_body():
    with pytest.raises(McpError):
        parse_response("<html>502 Bad Gateway</html>")


def test_tool_text_joins_content_parts():
    result = {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}

    assert tool_text(result) == "ab"


def test_tool_text_raises_on_tool_error():
    with pytest.raises(McpError, match="boom"):
        tool_text({"isError": True, "content": [{"type": "text", "text": "boom"}]})


def test_session_calls_use_json_rpc_shapes(monkeypatch):
    from scripts import mcp_client

    sent = []

    def fake_post(url, payload, session_id=None):
        sent.append(payload)
        reply = {"jsonrpc": "2.0", "id": payload.get("id"), "result": {"content": [{"type": "text", "text": "{}"}]}}
        return "sid-1", json.dumps(reply)

    monkeypatch.setattr(mcp_client, "_post", fake_post)

    session = mcp_client.McpSession("http://x/mcp")
    session.call_tool("get_quotation", {"quotation_id": 1})

    assert [p.get("method") for p in sent] == ["initialize", "notifications/initialized", "tools/call"]
    assert sent[-1]["params"] == {"name": "get_quotation", "arguments": {"quotation_id": 1}}
