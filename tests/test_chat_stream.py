import asyncio
import gc
import json

import pytest
from mcp import ClientSession
from mcp.types import CallToolResult, TextContent

from app.chat.events import ChatEvent
from app.chat.service import ChatService, ObservedClientSession


class FakeMcpSession(ObservedClientSession):
    """`ObservedClientSession` không có kết nối thật; `ClientSession.call_tool` được thay bằng `_fake_call_tool`."""

    def __init__(self, results=None, delay=0.0):
        self.results = results or {}
        self.delay = delay

    async def _fake_call_tool(self, name, arguments=None):
        await asyncio.sleep(self.delay)
        result = self.results.get(name)
        if isinstance(result, Exception):
            raise result
        return result or CallToolResult(content=[TextContent(type="text", text=json.dumps({"rows": [[1]], "row_count": 1}))])


@pytest.fixture(autouse=True)
def fake_parent_call_tool(monkeypatch):
    async def call_tool(self, name, arguments=None, *args, **kwargs):
        return await self._fake_call_tool(name, arguments)

    monkeypatch.setattr(ClientSession, "call_tool", call_tool)


class FakeResponse:
    def __init__(self, text):
        self.text = text


class ToolCallingChat:
    """Giả lập AsyncChat: gọi `session.call_tool` thật như SDK (lỗi tool thì nuốt và đưa `{'error': ...}` cho mô hình)."""

    def __init__(self, session, script):
        self.session = session
        self._script = script
        self.tasks = []
        self.tool_errors = []

    def get_history(self):
        return []

    async def send_message(self, question):
        self.tasks.append(asyncio.current_task())
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        for name, args in step.get("calls", []):
            try:
                await self.session.call_tool(name=name, arguments=args)
            except Exception as exc:
                self.tool_errors.append(str(exc))
        if step.get("hang"):
            await asyncio.Event().wait()
        if step.get("raise"):
            raise step["raise"]
        return FakeResponse(step.get("text"))


class FakeClient:
    def __init__(self, session, script):
        self.session = session
        self.script = script
        self.created = []
        self.aio = self
        self.chats = self

    def create(self, model, config):
        chat = ToolCallingChat(self.session, self.script)
        self.created.append(chat)
        return chat


def _service(script, session=None):
    session = session or FakeMcpSession()
    client = FakeClient(session, script)
    return ChatService(session, client, "mô-hình-thử"), client


async def _collect(service, question):
    return [event async for event in service.ask_stream(question)]


def _types(events):
    return [event.type for event in events]


def test_stream_emits_tool_events_in_order_then_answer_then_done():
    service, _ = _service([{"calls": [("run_readonly_sql", {"query": "SELECT 1"})], "text": "Có 1 dòng."}])

    events = asyncio.run(_collect(service, "Có bao nhiêu?"))

    assert _types(events) == ["tool_call", "tool_result", "answer", "done"]
    call, result, answer, done = events
    assert call.data == {"call_id": 1, "tool": "run_readonly_sql", "args": {"query": "SELECT 1"}}
    assert result.data["call_id"] == 1 and result.data["tool"] == "run_readonly_sql"
    assert result.data["ok"] is True and result.data["row_count"] == 1 and result.data["sql"] == "SELECT 1"
    assert isinstance(result.data["duration_ms"], int)
    assert answer.data == {"text": "Có 1 dòng."}
    assert isinstance(done.data["duration_ms"], int)
    for event in events:
        event.to_sse()  # dữ liệu phải tuần tự hoá được JSON


def test_call_ids_restart_at_one_for_each_question():
    service, _ = _service([
        {"calls": [("a", {}), ("b", {})], "text": "1"},
        {"calls": [("c", {})], "text": "2"},
    ])

    first = asyncio.run(_collect(service, "q1"))
    second = asyncio.run(_collect(service, "q2"))

    assert [e.data["call_id"] for e in first if e.type == "tool_call"] == [1, 2]
    assert [e.data["call_id"] for e in second if e.type == "tool_call"] == [1]


def test_tool_exception_emits_failed_result_and_stream_still_ends():
    session = FakeMcpSession(results={"broken": RuntimeError("db down")})
    service, client = _service([{"calls": [("broken", {"x": 1})], "text": "Không tra được."}], session)

    events = asyncio.run(asyncio.wait_for(_collect(service, "q"), timeout=2))

    assert _types(events) == ["tool_call", "tool_result", "answer", "done"]
    result = events[1].data
    assert result["ok"] is False and result["call_id"] == 1 and result["tool"] == "broken"
    assert "db down" in result["preview"]
    assert client.created[0].tool_errors == ["db down"]  # lỗi vẫn được ném lại cho SDK
    events[1].to_sse()


def test_gemini_failure_emits_error_model_and_no_done():
    service, client = _service([RuntimeError("quota exceeded"), {"text": "đã ổn"}])

    failed = asyncio.run(_collect(service, "q"))
    again = asyncio.run(_collect(service, "thử lại"))

    assert failed == [ChatEvent("error", {"code": "model", "message": "quota exceeded"})]
    assert _types(again) == ["answer", "done"] and again[0].data == {"text": "đã ổn"}
    assert len(client.created) == 1


def test_two_concurrent_streams_do_not_share_events():
    # Như production: một phiên MCP dùng chung cho mọi người xem, nên hàng đợi không được gắn vào đối tượng phiên.
    shared = FakeMcpSession(delay=0.01)
    service_a, _ = _service([{"calls": [("tool_a", {"n": 1}), ("tool_a", {"n": 2})], "text": "A"}], shared)
    service_b, _ = _service([{"calls": [("tool_b", {"n": 1})], "text": "B"}], shared)

    async def both():
        return await asyncio.gather(_collect(service_a, "a"), _collect(service_b, "b"))

    events_a, events_b = asyncio.run(both())

    assert [(e.type, e.data["call_id"], e.data["tool"]) for e in events_a if e.type.startswith("tool")] == [
        ("tool_call", 1, "tool_a"), ("tool_result", 1, "tool_a"), ("tool_call", 2, "tool_a"), ("tool_result", 2, "tool_a"),
    ]
    assert [(e.type, e.data["call_id"], e.data["tool"]) for e in events_b if e.type.startswith("tool")] == [
        ("tool_call", 1, "tool_b"), ("tool_result", 1, "tool_b"),
    ]
    assert events_a[-2].data == {"text": "A"} and events_b[-2].data == {"text": "B"}


def test_closing_the_stream_cancels_the_gemini_task():
    service, client = _service([{"calls": [("slow", {})], "hang": True}])

    async def run():
        stream = service.ask_stream("q")
        first = await stream.__anext__()
        await stream.aclose()
        task = client.created[0].tasks[0]
        others = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        return first, task, others

    first, task, others = asyncio.run(run())

    assert first.type == "tool_call"
    assert task.cancelled() is True
    assert others == []


def test_closing_early_after_gemini_failed_retrieves_the_task_error():
    service, client = _service([{"calls": [("t", {})], "raise": RuntimeError("quota exceeded")}])
    reported = []

    async def run():
        asyncio.get_running_loop().set_exception_handler(lambda loop, context: reported.append(context))
        stream = service.ask_stream("q")
        await stream.__anext__()
        task = client.created[0].tasks[0]
        await asyncio.wait({task})  # Gemini đã lỗi xong, nhưng người xem đóng luồng trước khi đọc tới kết quả
        await stream.aclose()

    asyncio.run(run())
    client.created[0].tasks.clear()  # bỏ tham chiếu cuối tới task để asyncio báo lỗi chưa đọc (nếu có) khi thu gom
    gc.collect()

    assert not any("never retrieved" in str(context.get("message")) for context in reported)


def test_tool_calls_without_a_stream_just_call_the_parent():
    session = FakeMcpSession()

    result = asyncio.run(session.call_tool(name="x", arguments={}))

    assert result.content[0].text == json.dumps({"rows": [[1]], "row_count": 1})


def test_non_json_args_are_turned_into_primitives():
    service, _ = _service([{"calls": [("t", {"when": object()})], "text": "ok"}])

    events = asyncio.run(_collect(service, "q"))

    assert isinstance(events[0].data["args"]["when"], str)
    events[0].to_sse()


class ParallelToolChat(ToolCallingChat):
    """Một phản hồi mô hình mang nhiều function_call song song; SDK chạy tất cả cùng lúc."""

    def __init__(self, session, calls):
        super().__init__(session, [])
        self.calls = calls
        self.results = []

    async def send_message(self, question):
        self.results = await asyncio.gather(
            *[self.session.call_tool(name=name, arguments=args) for name, args in self.calls]
        )
        return FakeResponse("xong")


def _parallel_service(calls, max_remote_calls=5):
    session = FakeMcpSession(delay=0.01)
    called = []
    original = session._fake_call_tool

    async def counting(name, arguments=None):
        called.append(name)
        return await original(name, arguments)

    session._fake_call_tool = counting
    client = FakeClient(session, [])
    chat = ParallelToolChat(session, calls)
    client.create = lambda model, config: chat
    return ChatService(session, client, "mô-hình-thử", max_remote_calls=max_remote_calls), chat, called


def test_tool_calls_beyond_the_per_question_limit_are_refused():
    calls = [(f"t{i}", {"i": i}) for i in range(1, 9)]
    service, chat, called = _parallel_service(calls)

    events = asyncio.run(_collect(service, "q"))

    tool_calls = [e for e in events if e.type == "tool_call"]
    tool_results = [e for e in events if e.type == "tool_result"]
    assert [e.data["call_id"] for e in tool_calls] == [1, 2, 3, 4, 5]
    assert sorted(e.data["call_id"] for e in tool_results) == [1, 2, 3, 4, 5]
    assert len(called) == 5  # MCP server chỉ bị gọi 5 lần
    refused = [r for r in chat.results if r.is_error]
    assert len(refused) == 3
    assert all(r.content[0].text == "tool-call limit reached" for r in refused)
    assert _types(events)[-2:] == ["answer", "done"]


def test_tool_calls_within_the_limit_are_unchanged():
    calls = [(f"t{i}", {}) for i in range(1, 6)]
    service, chat, called = _parallel_service(calls)

    events = asyncio.run(_collect(service, "q"))

    assert len(called) == 5
    assert not any(r.is_error for r in chat.results)
    assert sorted(e.data["call_id"] for e in events if e.type == "tool_result") == [1, 2, 3, 4, 5]


def test_tool_call_limit_follows_max_remote_calls_and_resets_per_question():
    calls = [(f"t{i}", {}) for i in range(1, 5)]
    service, chat, called = _parallel_service(calls, max_remote_calls=2)

    first = asyncio.run(_collect(service, "q1"))
    second = asyncio.run(_collect(service, "q2"))

    assert [e.data["call_id"] for e in first if e.type == "tool_call"] == [1, 2]
    assert [e.data["call_id"] for e in second if e.type == "tool_call"] == [1, 2]
    assert len(called) == 4
