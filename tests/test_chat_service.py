import asyncio

import pytest
from google.genai import types

from app.chat.service import (
    FALLBACK_ANSWER,
    SYSTEM_INSTRUCTION,
    ChatError,
    ChatService,
    MissingApiKeyError,
    build_service,
)


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeChat:
    """Giả lập AsyncChat của Gemini: tự gọi 'tool' rồi trả lời, và ghi lịch sử bằng đúng kiểu của SDK."""

    def __init__(self, script):
        self._history: list[types.Content] = []
        self._script = script

    def get_history(self):
        return list(self._history)

    async def send_message(self, question):
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        self._history.append(types.Content(role="user", parts=[types.Part(text=question)]))
        for name, args in step.get("calls", []):
            self._history.append(types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name=name, args=args))]))
            self._history.append(types.Content(role="user", parts=[types.Part(function_response=types.FunctionResponse(name=name, response={"ok": True}))]))
        self._history.append(types.Content(role="model", parts=[types.Part(text=step.get("text"))]))
        return FakeResponse(step.get("text"))


class FakeClient:
    def __init__(self, *scripts):
        self.created = []
        self._scripts = list(scripts)
        self.aio = self
        self.chats = self

    def create(self, model, config):
        chat = FakeChat(self._scripts.pop(0))
        self.created.append((model, config, chat))
        return chat


def _service(*scripts, **kwargs):
    session = object()
    client = FakeClient(*scripts)
    return ChatService(session, client, "mô-hình-thử", **kwargs), client, session


def test_ask_returns_the_answer_and_only_this_turns_tool_calls():
    service, _, _ = _service([
        {"calls": [("compare_work_item_price", {"item_id": 5})], "text": "Đắt hơn 10%."},
        {"calls": [("get_work_item", {"item_id": 5})], "text": "Đơn giá 244.814 đ."},
    ])

    first = asyncio.run(service.ask("A đắt hay rẻ?"))
    second = asyncio.run(service.ask("Đơn giá là bao nhiêu?"))

    assert first.answer == "Đắt hơn 10%."
    assert first.tool_calls == [{"tool": "compare_work_item_price", "args": {"item_id": 5}}]
    assert second.tool_calls == [{"tool": "get_work_item", "args": {"item_id": 5}}]


def test_chat_is_configured_with_the_instruction_the_mcp_session_and_a_call_limit():
    service, client, session = _service([{"text": "ok"}], max_remote_calls=7)

    asyncio.run(service.ask("hi"))

    model, config, _ = client.created[0]
    assert model == "mô-hình-thử"
    assert config.system_instruction == SYSTEM_INSTRUCTION
    assert "tiếng Việt" in SYSTEM_INSTRUCTION and "không tự bịa" in SYSTEM_INSTRUCTION
    assert config.tools == [session]
    assert config.automatic_function_calling.maximum_remote_calls == 7


def test_one_chat_serves_the_whole_session_until_reset():
    service, client, _ = _service([{"text": "1"}, {"text": "2"}], [{"text": "3"}])

    asyncio.run(service.ask("a"))
    asyncio.run(service.ask("b"))
    assert len(client.created) == 1
    service.reset()
    asyncio.run(service.ask("c"))

    assert len(client.created) == 2


def test_empty_model_text_falls_back_to_a_fixed_message():
    service, _, _ = _service([{"text": None}])

    assert asyncio.run(service.ask("hi")).answer == FALLBACK_ANSWER


def test_failure_raises_chat_error_and_the_session_stays_usable():
    service, client, _ = _service([RuntimeError("quota exceeded"), {"text": "đã ổn"}])

    with pytest.raises(ChatError, match="quota exceeded"):
        asyncio.run(service.ask("hi"))
    reply = asyncio.run(service.ask("thử lại"))

    assert reply.answer == "đã ổn" and len(client.created) == 1


def test_build_service_requires_an_api_key():
    with pytest.raises(MissingApiKeyError, match="GEMINI_API_KEY"):
        build_service(mcp_session=object(), api_key="", model="m")


def test_system_instruction_follows_the_language_of_the_question():
    assert "ngôn ngữ của câu hỏi" in SYSTEM_INSTRUCTION
    assert "tiếng Việt" in SYSTEM_INSTRUCTION
