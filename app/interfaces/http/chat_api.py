"""API chat cho website: `POST /chat/stream` (SSE) và `GET /chat/status`, chạy trên cổng riêng (xem `main_chat.py`).

Không ghi lại câu hỏi của người xem ở bất cứ đâu (không log, không file); lỗi gửi cho trình duyệt chỉ là thông báo chung,
chi tiết chỉ nằm trong log của server.
"""
import json
from typing import AsyncIterator, Callable

import anyio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.types import Send

from app.chat.events import ChatEvent
from app.chat.service import ChatService
from app.chat.sessions import SessionStore
from app.infrastructure.config.config import Settings, settings
from app.infrastructure.observability.logger import get_logger

logger = get_logger(__name__)

STREAM_HEADERS = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}
ERROR_MESSAGES = {
    "model": "Mô hình tạm thời không trả lời được, vui lòng thử lại sau.",
    "session_full": "Phiên hội thoại đã đạt số lượt hỏi tối đa, hãy bắt đầu phiên mới.",
    "internal": "Đã có lỗi xảy ra, vui lòng thử lại sau.",
}


def _error(code: str) -> ChatEvent:
    return ChatEvent("error", {"code": code, "message": ERROR_MESSAGES[code]})


class _ClosingStreamingResponse(StreamingResponse):
    """Luôn đóng (`aclose`) body iterator khi luồng kết thúc, kể cả khi người xem ngắt kết nối giữa chừng.

    Starlette không tự đóng generator; nếu nó đang dừng ở `yield` lúc gửi thất bại thì sẽ treo tới khi bị thu gom,
    kéo theo task Gemini. Đóng trong vùng được che chắn để việc huỷ không cắt ngang phần dọn dẹp.
    """

    async def stream_response(self, send: Send) -> None:
        try:
            await super().stream_response(send)
        finally:
            with anyio.CancelScope(shield=True):
                await self.body_iterator.aclose()


async def _read_question(request: Request) -> tuple[str | None, str | None]:
    """`(câu hỏi đã bỏ khoảng trắng hai đầu, session_id)`; body không hợp lệ thì câu hỏi là None."""
    try:
        body = json.loads(await request.body())
    except ValueError:
        return None, None
    if not isinstance(body, dict):
        return None, None
    message = body.get("message")
    session_id = body.get("session_id")
    return (
        message.strip() if isinstance(message, str) else None,
        session_id if isinstance(session_id, str) else None,
    )


async def _turn_events(store: SessionStore, requested_id: str | None, question: str) -> AsyncIterator[ChatEvent]:
    try:
        # Liền nhau, không `await` ở giữa: phiên vừa lấy không thể hết hạn hay bị đẩy ra trước khi có khóa.
        session_id, service = store.get_or_create(requested_id)
        lock = store.lock(session_id)
    except Exception:
        logger.exception("Could not open a chat session")
        yield _error("internal")
        return
    yield ChatEvent("start", {"session_id": session_id})
    async with lock:
        if store.is_full(session_id):
            yield _error("session_full")
            return
        finished = False
        try:
            stream = service.ask_stream(question)
            try:
                async for event in stream:
                    if event.type == "error":
                        code = event.data.get("code")
                        logger.warning("Chat turn failed: code=%s detail=%s", code, event.data.get("message"))
                        yield _error(code if code in ERROR_MESSAGES else "internal")
                        return
                    yield event
                    if event.type == "done":
                        finished = True
                        break
            finally:
                # Đóng luồng của dịch vụ để huỷ task Gemini nếu lượt hỏi dừng sớm (người xem ngắt kết nối).
                await stream.aclose()
        except Exception:
            logger.exception("Chat turn crashed")
            yield _error("internal")
            return
        if not finished:
            logger.error("Chat stream ended without done or error")
            yield _error("internal")
            return
        store.record_turn(session_id)


async def _sse(events: AsyncIterator[ChatEvent]) -> AsyncIterator[str]:
    try:
        async for event in events:
            yield event.to_sse()
    finally:
        await events.aclose()


def create_chat_app(service_factory: Callable[[], ChatService], settings_obj: Settings = settings) -> FastAPI:
    store = SessionStore(
        service_factory,
        ttl_seconds=settings_obj.chat_session_ttl_seconds,
        max_sessions=settings_obj.chat_max_sessions,
        max_turns=settings_obj.chat_max_turns_per_session,
    )
    app = FastAPI(title="Knowledge Base Chat API")
    app.state.sessions = store

    @app.get("/chat/status")
    def status() -> dict:
        return {"enabled": settings_obj.chat_demo_enabled}

    @app.post("/chat/stream")
    async def chat_stream(request: Request):
        """Body `{"message": str, "session_id": str | null}`; trả luồng SSE `start`, sự kiện của lượt hỏi, rồi `done`
        (hoặc `error` và đóng luồng). Lỗi kiểm tra đầu vào là JSON thường, trả trước khi tạo phiên hay gọi Gemini."""
        if not settings_obj.chat_demo_enabled:
            return JSONResponse({"code": "demo_disabled"}, status_code=503)
        question, session_id = await _read_question(request)
        if not question:
            return JSONResponse({"code": "invalid_question"}, status_code=422)
        if len(question) > settings_obj.chat_max_question_chars:
            return JSONResponse({"code": "too_long"}, status_code=422)
        return _ClosingStreamingResponse(
            _sse(_turn_events(store, session_id, question)),
            media_type="text/event-stream",
            headers=STREAM_HEADERS,
        )

    return app
