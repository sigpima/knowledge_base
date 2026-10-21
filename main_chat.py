"""Điểm vào của API chat cho website (SSE), chạy trên cổng riêng `chat_api_port`, tách khỏi API ingest có quyền ghi.

Cả tiến trình dùng chung một phiên MCP và một `genai.Client`; mỗi phiên hội thoại chỉ có đối tượng chat Gemini riêng.
"""
import asyncio
import sys
from contextlib import AsyncExitStack

import uvicorn

from app.chat.service import ChatService, build_service, mcp_session
from app.infrastructure.config.config import settings
from app.interfaces.http.chat_api import create_chat_app

NO_KEY_MESSAGE = "Chưa đặt GEMINI_API_KEY (biến môi trường hoặc file .env); API chat không thể chạy."


async def _serve() -> int:
    url = settings.mcp_server_url
    async with AsyncExitStack() as stack:
        try:
            session = await stack.enter_async_context(mcp_session(url))
        except Exception as exc:  # noqa: BLE001 -- lỗi kết nối nào cũng chỉ cần báo rõ cho người vận hành
            print(f"Không kết nối được MCP server tại {url} ({type(exc).__name__}).", file=sys.stderr)
            return 1
        shared = build_service(session, settings.gemini_api_key, settings.gemini_chat_model, settings.gemini_base_url)

        def service_factory() -> ChatService:
            return ChatService(shared.mcp_session, shared.gemini_client, shared.model, shared.max_remote_calls)

        app = create_chat_app(service_factory, settings_obj=settings)
        server = uvicorn.Server(uvicorn.Config(app, host=settings.chat_api_host, port=settings.chat_api_port))
        await server.serve()
    return 0


def main() -> int:
    if not settings.gemini_api_key:
        print(NO_KEY_MESSAGE, file=sys.stderr)
        return 2
    return asyncio.run(_serve())


if __name__ == "__main__":
    sys.exit(main())
