"""Hỏi đáp bằng Gemini: mô hình tự gọi các tool của MCP server (automatic function calling).

Lịch sử của phiên hiện tại nằm trong đối tượng chat của Gemini (RAM), nên hỏi tiếp được; `reset()` bắt đầu lại.
"""
import asyncio
import contextvars
import itertools
import json
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from google import genai
from google.genai import types
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.chat.events import PREVIEW_MAX_CHARS, SQL_TOOL, ChatEvent, summarize_tool_result
from app.infrastructure.observability.logger import get_logger

logger = get_logger(__name__)

FALLBACK_ANSWER = "Không có dữ liệu phù hợp để trả lời."

SYSTEM_INSTRUCTION = (
    "Bạn là trợ lý trả lời câu hỏi về dữ liệu báo giá và dự toán thi công sơn đã có sẵn trong hệ thống. "
    "Chỉ dùng các công cụ (tools) được cung cấp để tra cứu dữ liệu, không tự bịa thông tin. "
    "Mọi con số bạn nêu phải lấy nguyên từ kết quả công cụ; nếu công cụ không đủ dữ liệu để kết luận, hãy nói rõ giới hạn. "
    "Các trường *_diff của công cụ so sánh được tính là B trừ A. "
    "Trả lời ngắn gọn, chính xác, bằng ngôn ngữ của câu hỏi (mặc định tiếng Việt), nêu cụ thể tên công trình, đơn giá và tỷ lệ phần trăm."
)


class ChatError(RuntimeError):
    """Lượt hỏi thất bại (hết quota, mất mạng, công cụ lỗi...); phiên vẫn dùng tiếp được."""


class MissingApiKeyError(RuntimeError):
    pass


@dataclass
class ChatReply:
    answer: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class _LiveClientSession(ClientSession):
    """Phiên MCP là một tay cầm tài nguyên (luồng I/O + task nền), không phải dữ liệu để sao chép.

    `google-genai` deep-copy `GenerateContentConfig` (kể cả tool là phiên MCP) trước khi dùng; với phiên đang chạy việc đó
    luôn lỗi `cannot pickle '_asyncio.Task'`. Trả về chính nó khi bị sao chép là cách xử lý đúng.
    """

    def __deepcopy__(self, memo):
        return self


class _EventQueue(asyncio.Queue):
    """Hàng đợi sự kiện của một lượt hỏi; `call_id` đếm từ 1 trong lượt đó."""

    def __init__(self):
        super().__init__()
        self.call_ids = itertools.count(1)


# Mỗi lượt `ask_stream` đặt hàng đợi riêng; task Gemini sao chép ngữ cảnh lúc tạo nên chỉ thấy hàng đợi của lượt mình.
_event_queue: contextvars.ContextVar[_EventQueue | None] = contextvars.ContextVar("chat_event_queue", default=None)
_DONE = object()


def _primitive(value: Any) -> Any:
    """Đổi về kiểu JSON thuần (dict/list/str/số/bool/None) để `ChatEvent.to_sse` không lỗi."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


class ObservedClientSession(_LiveClientSession):
    """Phiên MCP phát `tool_call` rồi `tool_result` vào hàng đợi của lượt hỏi đang stream (nếu có).

    SDK gọi tool ngay trong task đang chờ `send_message`, nên đọc `ContextVar` ở đây lấy đúng hàng đợi của lượt đó.
    """

    async def call_tool(self, name, arguments=None, *args, **kwargs):
        queue = _event_queue.get()
        if queue is None:
            return await super().call_tool(name, arguments, *args, **kwargs)
        call_id = next(queue.call_ids)
        tool_args = _primitive(arguments or {})
        queue.put_nowait(ChatEvent("tool_call", {"call_id": call_id, "tool": name, "args": tool_args}))
        started = time.perf_counter()
        try:
            result = await super().call_tool(name, arguments, *args, **kwargs)
        except Exception as exc:
            # SDK tự bắt lỗi và đưa `{'error': ...}` cho mô hình; ở đây chỉ báo cho client rồi ném lại.
            summary = {
                "ok": False,
                "row_count": None,
                "sql": tool_args.get("query") if name == SQL_TOOL else None,
                "preview": (str(exc) or type(exc).__name__)[:PREVIEW_MAX_CHARS],
            }
            queue.put_nowait(self._result_event(call_id, name, started, summary))
            raise
        summary = summarize_tool_result(name, tool_args, result)
        queue.put_nowait(self._result_event(call_id, name, started, summary))
        return result

    @staticmethod
    def _result_event(call_id: int, name: str, started: float, summary: dict) -> ChatEvent:
        data = {"call_id": call_id, "tool": name, "duration_ms": _elapsed_ms(started), **summary}
        return ChatEvent("tool_result", _primitive(data))


@asynccontextmanager
async def mcp_session(url: str) -> AsyncIterator[ClientSession]:
    async with streamable_http_client(url) as (read_stream, write_stream, *_):
        async with ObservedClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield session


def _extract_tool_calls(history: list[types.Content]) -> list[dict[str, Any]]:
    calls = []
    for content in history:
        for part in content.parts or []:
            if part.function_call is not None:
                calls.append({"tool": part.function_call.name, "args": dict(part.function_call.args or {})})
    return calls


class ChatService:
    def __init__(self, mcp_session: ClientSession, gemini_client: genai.Client, model: str, max_remote_calls: int = 5):
        self.mcp_session = mcp_session
        self.gemini_client = gemini_client
        self.model = model
        self.max_remote_calls = max_remote_calls
        self._chat = None

    def _config(self) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[self.mcp_session],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=self.max_remote_calls),
        )

    def reset(self) -> None:
        self._chat = None

    def _get_chat(self):
        if self._chat is None:
            self._chat = self.gemini_client.aio.chats.create(model=self.model, config=self._config())
        return self._chat

    async def ask(self, question: str) -> ChatReply:
        chat = self._get_chat()
        history_before = len(chat.get_history())
        try:
            response = await chat.send_message(question)
        except Exception as exc:
            logger.warning("Gemini chat call failed", exc_info=True)
            raise ChatError(str(exc) or type(exc).__name__) from exc
        # AsyncChat tự chạy vòng gọi tool và chỉ ghi các lượt gọi vào lịch sử của chat, nên đọc phần mới thêm ở đó.
        return ChatReply(
            answer=response.text or FALLBACK_ANSWER,
            tool_calls=_extract_tool_calls(chat.get_history()[history_before:]),
        )

    async def ask_stream(self, question: str) -> AsyncIterator[ChatEvent]:
        """Phát `tool_call`/`tool_result` trong lúc Gemini chạy, rồi `answer` và `done`; Gemini lỗi thì chỉ phát `error`.

        `start` do tầng HTTP phát (nó mới biết session id). Đóng generator sớm sẽ huỷ task Gemini.
        """
        started = time.perf_counter()
        chat = self._get_chat()
        queue = _EventQueue()
        token = _event_queue.set(queue)
        try:
            task = asyncio.create_task(chat.send_message(question))
        finally:
            _event_queue.reset(token)
        task.add_done_callback(lambda _: queue.put_nowait(_DONE))
        try:
            while (event := await queue.get()) is not _DONE:
                yield event
            try:
                response = task.result()
            except Exception as exc:
                logger.warning("Gemini chat call failed", exc_info=True)
                yield ChatEvent("error", {"code": "model", "message": str(exc) or type(exc).__name__})
                return
            yield ChatEvent("answer", {"text": response.text or FALLBACK_ANSWER})
            yield ChatEvent("done", {"duration_ms": _elapsed_ms(started)})
        finally:
            if not task.done():
                task.cancel()
                # `asyncio.wait` không ném lỗi của task, nhưng nếu chính task gọi bị huỷ thì vẫn để huỷ lan ra ngoài.
                await asyncio.wait({task})
                if not task.cancelled():
                    task.exception()  # đã đọc lỗi để asyncio không cảnh báo "never retrieved"

    async def tool_names(self) -> list[str]:
        return [tool.name for tool in (await self.mcp_session.list_tools()).tools]


def build_service(mcp_session: ClientSession, api_key: str, model: str, base_url: str = "") -> ChatService:
    if not api_key:
        raise MissingApiKeyError("Chưa có GEMINI_API_KEY")
    options = types.HttpOptions(base_url=base_url) if base_url else None
    return ChatService(mcp_session, genai.Client(api_key=api_key, http_options=options), model)
