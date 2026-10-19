"""Chạy thật đoạn khó nhất mà không cần khoá API: SDK Gemini thật + MCP server thật + server Gemini giả cục bộ.

Server giả trả về một lệnh gọi tool ở lượt đầu và, khi đã thấy kết quả tool, một câu trả lời có chứa con số lấy từ kết quả đó.
Nhờ vậy test chứng minh được kết quả tool thật đã đi đúng đường MCP -> SDK -> mô hình -> câu trả lời.
"""
import asyncio
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from google import genai
from google.genai import types
from sqlalchemy import text

from app.chat import cli
from app.chat.service import ChatService, mcp_session
from app.infrastructure.database.postgres.session import SessionLocal, engine
from scripts.mcp_client import McpSession
from scripts.seed import seed

ROOT = Path(__file__).resolve().parent.parent
QUERY = "SELECT count(*) AS projects FROM quotation.project"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def mcp_url(db_engine):
    seed(SessionLocal, ROOT / "data" / "sample")
    port = _free_port()
    env = {
        **os.environ,
        "DATABASE_URL_READONLY": os.environ["TEST_DATABASE_URL_READONLY"],
        "MCP_SERVER_PORT": str(port),
        "MCP_SERVER_HOST": "127.0.0.1",
    }
    server = subprocess.Popen([sys.executable, "main_mcp.py"], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}/mcp"
    try:
        for _ in range(100):
            try:
                McpSession(url)
                break
            except Exception:
                if server.poll() is not None:
                    raise RuntimeError(server.stdout.read().decode("utf-8", "replace"))
                time.sleep(0.2)
        else:
            raise RuntimeError("MCP server không lên kịp")
        yield url
    finally:
        server.terminate()
        server.wait(timeout=10)
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE quotation.project RESTART IDENTITY CASCADE"))


class _FakeGemini(BaseHTTPRequestHandler):
    bodies: list = []

    def do_POST(self):  # noqa: N802 -- tên do http.server quy định
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).bodies.append(body)
        if not self.path.endswith(":generateContent"):
            self.send_error(404)
            return
        parts = [part for content in body["contents"] for part in content.get("parts", [])]
        results = [part["functionResponse"] for part in parts if "functionResponse" in part]
        if results:
            count = re.search(r"projects\W+(\d+)", json.dumps(results[-1], ensure_ascii=False))
            reply_part = {"text": f"Có {count.group(1)} công trình."}
        else:
            reply_part = {"functionCall": {"name": "run_readonly_sql", "args": {"query": QUERY}}}
        payload = json.dumps({"candidates": [{"content": {"role": "model", "parts": [reply_part]}, "finishReason": "STOP"}]})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload.encode("utf-8"))

    def log_message(self, *args):
        pass


@pytest.fixture
def fake_gemini():
    _FakeGemini.bodies = []
    server = HTTPServer(("127.0.0.1", 0), _FakeGemini)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", _FakeGemini
    server.shutdown()


def _client(base_url: str):
    return genai.Client(api_key="fake-key", http_options=types.HttpOptions(base_url=base_url))


def test_sdk_runs_the_real_mcp_tool_and_the_answer_uses_its_result(mcp_url, fake_gemini):
    base_url, fake = fake_gemini

    async def go():
        async with mcp_session(mcp_url) as session:
            service = ChatService(session, _client(base_url), "gemini-giả")
            return await service.ask("Có bao nhiêu công trình?"), await service.tool_names()

    reply, tool_names = asyncio.run(go())

    assert reply.answer == "Có 24 công trình."
    assert reply.tool_calls == [{"tool": "run_readonly_sql", "args": {"query": QUERY}}]
    assert len(fake.bodies) == 2
    assert "tiếng Việt" in json.dumps(fake.bodies[0], ensure_ascii=False)  # system instruction đã được gửi
    assert len(tool_names) == 10 and "compare_work_item_price" in tool_names


def test_main_runs_a_whole_terminal_session(mcp_url, fake_gemini, monkeypatch, capsys, tmp_path):
    base_url, _ = fake_gemini
    monkeypatch.setattr(cli.settings, "gemini_api_key", "fake-key")
    monkeypatch.setattr(cli.settings, "gemini_base_url", base_url)
    answers = iter(["Có bao nhiêu công trình?", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    code = cli.main(["--url", mcp_url, "--log-dir", str(tmp_path)])

    assert code == 0
    out = capsys.readouterr().out
    assert "Có 24 công trình." in out and "run_readonly_sql" in out
    (log_file,) = tmp_path.glob("chat-*.json")
    turns = json.loads(log_file.read_text(encoding="utf-8"))
    assert [(t["question"], t["answer"]) for t in turns] == [("Có bao nhiêu công trình?", "Có 24 công trình.")]
