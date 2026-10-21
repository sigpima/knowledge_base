import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.chat.events import ChatEvent
from app.infrastructure.config.config import Settings
from app.interfaces.http.chat_api import create_chat_app

SECRET = "sk-SECRET-upstream-detail-42"


def make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        if not block:
            continue
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((lines["event"], json.loads(lines["data"])))
    return events


class FakeService:
    """Phát một chuỗi sự kiện định sẵn; ghi lại câu hỏi và việc generator có bị đóng hay không."""

    def __init__(self, events=None, raise_exc=None):
        self.events = events if events is not None else [
            ChatEvent("tool_call", {"call_id": 1, "tool": "run_readonly_sql", "args": {"query": "SELECT 1"}}),
            ChatEvent("tool_result", {"call_id": 1, "tool": "run_readonly_sql", "ok": True, "duration_ms": 3,
                                      "row_count": 1, "sql": "SELECT 1", "preview": "1"}),
            ChatEvent("answer", {"text": "Có 24 công trình."}),
            ChatEvent("done", {"duration_ms": 10}),
        ]
        self.raise_exc = raise_exc
        self.questions = []
        self.closed = False

    async def ask_stream(self, question):
        self.questions.append(question)
        try:
            for event in self.events:
                yield event
            if self.raise_exc is not None:
                raise self.raise_exc
        finally:
            self.closed = True


class Factory:
    def __init__(self, make=FakeService):
        self.make = make
        self.created = []

    def __call__(self):
        service = self.make()
        self.created.append(service)
        return service


def post(client, message, session_id=None):
    return client.post("/chat/stream", json={"message": message, "session_id": session_id})


def test_status_reflects_enabled_flag():
    with TestClient(create_chat_app(Factory(), make_settings(chat_demo_enabled=True))) as client:
        assert client.get("/chat/status").json() == {"enabled": True}
    with TestClient(create_chat_app(Factory(), make_settings(chat_demo_enabled=False))) as client:
        assert client.get("/chat/status").json() == {"enabled": False}


def test_disabled_returns_503_demo_disabled():
    factory = Factory()
    with TestClient(create_chat_app(factory, make_settings(chat_demo_enabled=False))) as client:
        response = post(client, "   ")  # tắt demo được kiểm tra trước cả câu hỏi rỗng
    assert response.status_code == 503
    assert response.json() == {"code": "demo_disabled"}
    assert factory.created == []


@pytest.mark.parametrize("body", [{"message": ""}, {"message": "  \n\t "}, {}, {"message": 5}, None])
def test_blank_question_returns_422_invalid_question(body):
    factory = Factory()
    with TestClient(create_chat_app(factory, make_settings())) as client:
        if body is None:
            response = client.post("/chat/stream", content=b"not json", headers={"content-type": "application/json"})
        else:
            response = client.post("/chat/stream", json=body)
    assert response.status_code == 422
    assert response.json() == {"code": "invalid_question"}
    assert factory.created == []


def test_overlong_question_returns_422_too_long():
    factory = Factory()
    with TestClient(create_chat_app(factory, make_settings())) as client:
        response = post(client, "a" * 501)
        ok = post(client, "a" * 500)
    assert response.status_code == 422
    assert response.json() == {"code": "too_long"}
    assert ok.status_code == 200
    assert len(factory.created) == 1


def test_stream_starts_with_start_event_and_ends_with_done():
    factory = Factory()
    with TestClient(create_chat_app(factory, make_settings())) as client:
        response = post(client, "  Có bao nhiêu công trình?  ")
    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["start", "tool_call", "tool_result", "answer", "done"]
    assert isinstance(events[0][1]["session_id"], str) and events[0][1]["session_id"]
    assert events[3][1] == {"text": "Có 24 công trình."}
    assert factory.created[0].questions == ["Có bao nhiêu công trình?"]


def test_same_session_id_reuses_the_service():
    factory = Factory()
    with TestClient(create_chat_app(factory, make_settings())) as client:
        first = parse_sse(post(client, "câu 1").text)[0][1]["session_id"]
        second = parse_sse(post(client, "câu 2", first).text)[0][1]["session_id"]
    assert second == first
    assert len(factory.created) == 1
    assert factory.created[0].questions == ["câu 1", "câu 2"]


def test_unknown_session_id_gets_a_new_one_in_start():
    with TestClient(create_chat_app(Factory(), make_settings())) as client:
        response = post(client, "xin chào", "khong-ton-tai")
    assert response.status_code == 200
    start = parse_sse(response.text)[0]
    assert start[0] == "start"
    assert start[1]["session_id"] not in ("", "khong-ton-tai")


def test_session_full_emits_error_session_full():
    factory = Factory()
    with TestClient(create_chat_app(factory, make_settings(chat_max_turns_per_session=1))) as client:
        session_id = parse_sse(post(client, "câu 1").text)[0][1]["session_id"]
        events = parse_sse(post(client, "câu 2", session_id).text)
    assert [name for name, _ in events] == ["start", "error"]
    assert events[0][1] == {"session_id": session_id}
    assert events[1][1]["code"] == "session_full"
    assert factory.created[0].questions == ["câu 1"]


def test_failed_turn_does_not_count_toward_the_session_limit():
    factory = Factory(lambda: FakeService(events=[ChatEvent("error", {"code": "model", "message": "quota"})]))
    with TestClient(create_chat_app(factory, make_settings(chat_max_turns_per_session=1))) as client:
        session_id = parse_sse(post(client, "câu 1").text)[0][1]["session_id"]
        events = parse_sse(post(client, "câu 2", session_id).text)
    assert [name for name, _ in events] == ["start", "error"]
    assert events[1][1]["code"] == "model"
    assert factory.created[0].questions == ["câu 1", "câu 2"]


def test_stream_headers():
    with TestClient(create_chat_app(Factory(), make_settings())) as client:
        response = post(client, "xin chào")
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["x-accel-buffering"] == "no"


def test_nothing_is_written_to_chat_logs_dir(tmp_path):
    log_dir = tmp_path / "chat_logs"
    log_dir.mkdir()
    with TestClient(create_chat_app(Factory(), make_settings(chat_log_dir=str(log_dir)))) as client:
        assert post(client, "xin chào").status_code == 200
    assert list(log_dir.iterdir()) == []


def test_model_error_message_is_generic_and_details_are_logged(caplog):
    factory = Factory(lambda: FakeService(events=[ChatEvent("error", {"code": "model", "message": SECRET})]))
    with TestClient(create_chat_app(factory, make_settings())) as client:
        response = post(client, "câu hỏi riêng tư")
    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["start", "error"]
    assert events[1][1]["code"] == "model"
    assert events[1][1]["message"]
    assert SECRET not in response.text
    assert SECRET in caplog.text
    assert "câu hỏi riêng tư" not in caplog.text


def test_unexpected_exception_becomes_generic_internal_error(caplog):
    factory = Factory(lambda: FakeService(events=[ChatEvent("answer", {"text": "x"})], raise_exc=RuntimeError(SECRET)))
    with TestClient(create_chat_app(factory, make_settings())) as client:
        response = post(client, "câu hỏi riêng tư")
    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["start", "answer", "error"]
    assert events[2][1]["code"] == "internal"
    assert SECRET not in response.text
    assert SECRET in caplog.text
    assert "câu hỏi riêng tư" not in caplog.text


def test_stream_that_ends_without_done_or_error_reports_internal():
    factory = Factory(lambda: FakeService(events=[ChatEvent("answer", {"text": "x"})]))
    with TestClient(create_chat_app(factory, make_settings(chat_max_turns_per_session=1))) as client:
        response = post(client, "câu 1")
        session_id = parse_sse(response.text)[0][1]["session_id"]
        again = parse_sse(post(client, "câu 2", session_id).text)
    assert [name for name, _ in parse_sse(response.text)] == ["start", "answer", "error"]
    assert parse_sse(response.text)[2][1]["code"] == "internal"
    assert [name for name, _ in again] == ["start", "answer", "error"]  # lượt hỏng không bị tính


def test_lost_session_becomes_internal_error_not_a_500():
    app = create_chat_app(Factory(), make_settings())

    def lost(session_id):
        raise KeyError(session_id)

    app.state.sessions.lock = lost
    with TestClient(app, raise_server_exceptions=False) as client:
        response = post(client, "xin chào")
    assert response.status_code == 200
    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["error"]
    assert events[0][1]["code"] == "internal"


def test_two_requests_on_the_same_session_are_serialized():
    state = {"active": 0, "max_active": 0}

    class SlowService(FakeService):
        async def ask_stream(self, question):
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
            try:
                await asyncio.sleep(0.05)
                yield ChatEvent("answer", {"text": question})
                yield ChatEvent("done", {"duration_ms": 1})
            finally:
                state["active"] -= 1

    app = create_chat_app(Factory(SlowService), make_settings())

    async def go():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post("/chat/stream", json={"message": "câu 0"})
            session_id = parse_sse(first.text)[0][1]["session_id"]
            state["max_active"] = 0
            return await asyncio.gather(*[
                client.post("/chat/stream", json={"message": f"câu {i}", "session_id": session_id}) for i in (1, 2)
            ])

    responses = asyncio.run(go())
    assert state["max_active"] == 1
    for response in responses:
        assert [name for name, _ in parse_sse(response.text)] == ["start", "answer", "done"]


class HangingService:
    """Phát một sự kiện rồi chờ mãi như Gemini đang chạy; ghi lại việc generator bị đóng."""

    def __init__(self):
        self.closed = False

    async def ask_stream(self, question):
        try:
            yield ChatEvent("tool_call", {"call_id": 1, "tool": "t", "args": {}})
            yield ChatEvent("tool_result", {"call_id": 1, "tool": "t", "ok": True})
            await asyncio.Event().wait()
        finally:
            self.closed = True


@pytest.mark.parametrize("spec_version", ["2.4", "2.3"])
def test_client_disconnect_closes_the_service_stream(spec_version):
    factory = Factory(HangingService)
    app = create_chat_app(factory, make_settings())
    body = json.dumps({"message": "xin chào"}).encode()

    async def go():
        first_chunk = asyncio.Event()
        requested = False

        async def receive():
            nonlocal requested
            if not requested:
                requested = True
                return {"type": "http.request", "body": body, "more_body": False}
            await first_chunk.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.body" and message.get("body"):
                if first_chunk.is_set() and spec_version == "2.4":
                    raise OSError("client went away")
                first_chunk.set()

        scope = {
            "type": "http", "asgi": {"version": "3.0", "spec_version": spec_version}, "http_version": "1.1",
            "method": "POST", "scheme": "http", "path": "/chat/stream", "raw_path": b"/chat/stream",
            "query_string": b"", "root_path": "", "headers": [(b"content-type", b"application/json")],
            "client": ("127.0.0.1", 1), "server": ("127.0.0.1", 8003),
        }
        try:
            await asyncio.wait_for(app(scope, receive, send), timeout=5)
        except Exception:  # ClientDisconnect / OSError chỉ là cách ngắt kết nối được báo lên
            pass
        # Kiểm tra ngay trong vòng lặp: `asyncio.run` tự đóng mọi async generator còn treo khi kết thúc.
        return factory.created[0].closed

    assert asyncio.run(go()) is True


def test_main_chat_exits_with_a_clear_message_without_api_key(monkeypatch, capsys):
    import main_chat

    monkeypatch.setattr(main_chat.settings, "gemini_api_key", "")
    assert main_chat.main() == 2
    assert "GEMINI_API_KEY" in capsys.readouterr().err


def test_main_chat_shares_one_mcp_session_and_one_gemini_client(monkeypatch):
    from contextlib import asynccontextmanager

    import uvicorn

    import main_chat

    opened = []
    captured = {}

    @asynccontextmanager
    async def fake_mcp_session(url):
        opened.append(url)
        yield object()

    def fake_create_chat_app(factory, settings_obj):
        captured["factory"] = factory
        return "app"

    async def fake_serve(self, *args, **kwargs):
        captured["config"] = self.config

    monkeypatch.setattr(main_chat.settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(main_chat, "mcp_session", fake_mcp_session)
    monkeypatch.setattr(main_chat, "create_chat_app", fake_create_chat_app)
    monkeypatch.setattr(uvicorn.Server, "serve", fake_serve)

    assert main_chat.main() == 0
    assert opened == [main_chat.settings.mcp_server_url]
    first, second = captured["factory"](), captured["factory"]()
    assert first is not second
    assert first.gemini_client is second.gemini_client
    assert first.mcp_session is second.mcp_session
    assert captured["config"].host == main_chat.settings.chat_api_host
    assert captured["config"].port == main_chat.settings.chat_api_port
