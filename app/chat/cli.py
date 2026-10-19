"""Vòng lặp hỏi–đáp trong terminal: `python -m app.chat`."""
import argparse
import asyncio
import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Callable

from app.chat.history import ChatHistoryLog, new_session_path
from app.chat.service import ChatError, MissingApiKeyError, build_service, mcp_session
from app.infrastructure.config.config import settings

EXIT_COMMANDS = {"/exit", "/quit", "exit", "quit"}
HELP = (
    "Gõ câu hỏi bằng tiếng Việt rồi Enter. Lệnh: /tools (liệt kê công cụ), /clear (xoá ngữ cảnh, hỏi lại từ đầu), "
    "/help, /exit (hoặc Ctrl-D)."
)
NO_KEY_MESSAGE = (
    "Chưa có GEMINI_API_KEY. Lấy khoá tại https://aistudio.google.com/apikey rồi chạy:\n"
    "  export GEMINI_API_KEY=...   (hoặc ghi vào file .env)\n"
    "  python -m app.chat"
)


def _describe_call(call: dict) -> str:
    args = json.dumps(call["args"], ensure_ascii=False)
    return f"  ↳ {call['tool']} {args if len(args) <= 160 else args[:157] + '...'}"


async def run_repl(
    service,
    log: ChatHistoryLog | None,
    *,
    input_fn: Callable[[str], str] | None = None,
    print_fn: Callable[[str], None] | None = None,
    show_tool_calls: bool = True,
) -> None:
    input_fn = input_fn or input  # tra lúc chạy (không gắn cứng lúc định nghĩa) để thay thế được khi thử
    print_fn = print_fn or print
    print_fn(HELP)
    while True:
        try:
            line = (await asyncio.to_thread(input_fn, "\nbạn> ")).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line in EXIT_COMMANDS:
            break
        if line == "/help":
            print_fn(HELP)
        elif line == "/clear":
            service.reset()
            print_fn("Đã xoá ngữ cảnh; câu hỏi tiếp theo bắt đầu cuộc trò chuyện mới.")
        elif line == "/tools":
            print_fn("\n".join(f"- {name}" for name in await service.tool_names()))
        elif line.startswith("/"):
            print_fn(f"Không biết lệnh {line.split()[0]!r}. {HELP}")
        else:
            try:
                reply = await service.ask(line)
            except ChatError as exc:
                print_fn(f"Lỗi khi hỏi mô hình: {exc}")
                continue
            if show_tool_calls:
                for call in reply.tool_calls:
                    print_fn(_describe_call(call))
            print_fn(f"\n{reply.answer}")
            if log is not None:
                log.append_turn(line, reply.answer, reply.tool_calls)


async def _run(args: argparse.Namespace) -> int:
    url = args.url or settings.mcp_server_url
    async with AsyncExitStack() as stack:
        try:
            session = await stack.enter_async_context(mcp_session(url))
        except Exception as exc:  # noqa: BLE001 -- lỗi kết nối nào cũng chỉ cần báo rõ cho người dùng
            print(f"Không kết nối được MCP server tại {url} ({type(exc).__name__}). "
                  "Đã chạy `docker compose up` chưa?", file=sys.stderr)
            return 1
        service = build_service(
            session, settings.gemini_api_key, args.model or settings.gemini_chat_model, settings.gemini_base_url
        )
        log = None
        if not args.no_log:
            path = new_session_path(Path(args.log_dir or settings.chat_log_dir))
            log = ChatHistoryLog(path)
            print(f"(lịch sử phiên này được ghi vào {path})")
        await run_repl(service, log, show_tool_calls=not args.quiet)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.chat", description="Hỏi đáp về dữ liệu báo giá bằng Gemini + MCP.")
    parser.add_argument("--url", help=f"địa chỉ MCP server (mặc định {settings.mcp_server_url})")
    parser.add_argument("--model", help=f"mô hình Gemini (mặc định {settings.gemini_chat_model})")
    parser.add_argument("--log-dir", help=f"thư mục ghi lịch sử JSON (mặc định {settings.chat_log_dir})")
    parser.add_argument("--no-log", action="store_true", help="không ghi lịch sử ra file")
    parser.add_argument("--quiet", action="store_true", help="không in các lần gọi công cụ")
    args = parser.parse_args(argv)

    if not settings.gemini_api_key:
        print(NO_KEY_MESSAGE, file=sys.stderr)
        return 2
    try:
        import readline  # noqa: F401 -- chỉ để input() có phím mũi tên và lịch sử dòng
    except ImportError:
        pass
    try:
        return asyncio.run(_run(args))
    except MissingApiKeyError as exc:
        print(exc, file=sys.stderr)
        return 2
