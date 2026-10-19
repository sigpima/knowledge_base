"""Hỏi đáp bằng Gemini: mô hình tự gọi các tool của MCP server (automatic function calling).

Lịch sử của phiên hiện tại nằm trong đối tượng chat của Gemini (RAM), nên hỏi tiếp được; `reset()` bắt đầu lại.
"""
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from google import genai
from google.genai import types
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.infrastructure.observability.logger import get_logger

logger = get_logger(__name__)

FALLBACK_ANSWER = "Không có dữ liệu phù hợp để trả lời."

SYSTEM_INSTRUCTION = (
    "Bạn là trợ lý trả lời câu hỏi về dữ liệu báo giá và dự toán thi công sơn đã có sẵn trong hệ thống. "
    "Chỉ dùng các công cụ (tools) được cung cấp để tra cứu dữ liệu, không tự bịa thông tin. "
    "Mọi con số bạn nêu phải lấy nguyên từ kết quả công cụ; nếu công cụ không đủ dữ liệu để kết luận, hãy nói rõ giới hạn. "
    "Các trường *_diff của công cụ so sánh được tính là B trừ A. "
    "Trả lời ngắn gọn, chính xác, bằng tiếng Việt, nêu cụ thể tên công trình, đơn giá và tỷ lệ phần trăm."
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


@asynccontextmanager
async def mcp_session(url: str) -> AsyncIterator[ClientSession]:
    async with streamable_http_client(url) as (read_stream, write_stream, *_):
        async with _LiveClientSession(read_stream, write_stream) as session:
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

    async def ask(self, question: str) -> ChatReply:
        if self._chat is None:
            self._chat = self.gemini_client.aio.chats.create(model=self.model, config=self._config())
        chat = self._chat
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

    async def tool_names(self) -> list[str]:
        return [tool.name for tool in (await self.mcp_session.list_tools()).tools]


def build_service(mcp_session: ClientSession, api_key: str, model: str, base_url: str = "") -> ChatService:
    if not api_key:
        raise MissingApiKeyError("Chưa có GEMINI_API_KEY")
    options = types.HttpOptions(base_url=base_url) if base_url else None
    return ChatService(mcp_session, genai.Client(api_key=api_key, http_options=options), model)
