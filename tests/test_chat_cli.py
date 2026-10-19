import asyncio
import json
from types import SimpleNamespace

from app.chat import cli
from app.chat.history import ChatHistoryLog
from app.chat.service import ChatError, ChatReply


class FakeService:
    def __init__(self, replies):
        self.replies = list(replies)
        self.asked = []
        self.resets = 0

    async def ask(self, question):
        self.asked.append(question)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def reset(self):
        self.resets += 1

    async def tool_names(self):
        return ["get_quotation", "run_readonly_sql"]


def _run(service, lines, log=None, **kwargs):
    inputs = iter(lines)

    def fake_input(prompt):
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    out = []
    asyncio.run(cli.run_repl(service, log, input_fn=fake_input, print_fn=out.append, **kwargs))
    return "\n".join(out)


def test_question_is_answered_with_tool_calls_shown_and_the_turn_logged(tmp_path):
    reply = ChatReply("Có 24 công trình.", [{"tool": "run_readonly_sql", "args": {"query": "SELECT 1"}}])
    service, log = FakeService([reply]), ChatHistoryLog(tmp_path / "s.json")

    output = _run(service, ["Có bao nhiêu công trình?", "/exit"], log)

    assert service.asked == ["Có bao nhiêu công trình?"]
    assert "run_readonly_sql" in output and "Có 24 công trình." in output
    turns = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    assert [(t["question"], t["answer"]) for t in turns] == [("Có bao nhiêu công trình?", "Có 24 công trình.")]
    assert turns[0]["tool_calls"] == reply.tool_calls


def test_quiet_hides_tool_calls_but_still_logs_them(tmp_path):
    reply = ChatReply("ok", [{"tool": "get_quotation", "args": {"quotation_id": 1}}])
    log = ChatHistoryLog(tmp_path / "s.json")

    output = _run(FakeService([reply]), ["hi"], log, show_tool_calls=False)

    assert "get_quotation" not in output
    assert json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))[0]["tool_calls"] == reply.tool_calls


def test_blank_lines_are_ignored_and_eof_ends_the_session():
    service = FakeService([])

    _run(service, ["", "   "])

    assert service.asked == []


def test_clear_resets_the_conversation():
    service = FakeService([])

    output = _run(service, ["/clear", "/exit"])

    assert service.resets == 1 and "xoá" in output.lower()


def test_tools_command_lists_tool_names():
    output = _run(FakeService([]), ["/tools", "/exit"])

    assert "get_quotation" in output and "run_readonly_sql" in output


def test_help_and_unknown_slash_commands_do_not_reach_the_model():
    service = FakeService([])

    output = _run(service, ["/help", "/nope", "/exit"])

    assert service.asked == [] and "/clear" in output and "/nope" in output


def test_a_failed_question_prints_the_error_logs_nothing_and_the_loop_continues(tmp_path):
    service = FakeService([ChatError("hết quota"), ChatReply("đã ổn", [])])
    log = ChatHistoryLog(tmp_path / "s.json")

    output = _run(service, ["một", "hai"], log)

    assert "hết quota" in output and "đã ổn" in output
    assert [t["question"] for t in json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))] == ["hai"]


def test_main_without_an_api_key_explains_how_to_set_it(monkeypatch, capsys):
    monkeypatch.setattr(cli.settings, "gemini_api_key", "")

    code = cli.main([])

    assert code == 2
    assert "GEMINI_API_KEY" in capsys.readouterr().err


def test_main_reports_an_unreachable_mcp_server(monkeypatch, capsys):
    monkeypatch.setattr(cli.settings, "gemini_api_key", "fake")

    code = cli.main(["--url", "http://127.0.0.1:1/mcp"])

    assert code == 1
    assert "MCP" in capsys.readouterr().err
