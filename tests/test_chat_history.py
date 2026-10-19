import json
from datetime import datetime, timezone

from app.chat.history import ChatHistoryLog, new_session_path


def test_new_session_path_is_timestamped_inside_the_log_dir(tmp_path):
    now = datetime(2026, 10, 20, 9, 5, 7, tzinfo=timezone.utc)

    path = new_session_path(tmp_path / "chat_logs", now=now)

    assert path == tmp_path / "chat_logs" / "chat-20261020-090507.json"


def test_append_turn_writes_a_json_list_and_keeps_vietnamese_readable(tmp_path):
    log = ChatHistoryLog(tmp_path / "logs" / "s.json")

    log.append_turn("Có bao nhiêu công trình?", "Có 24 công trình.", [{"tool": "run_readonly_sql", "args": {"query": "SELECT 1"}}])

    raw = (tmp_path / "logs" / "s.json").read_text(encoding="utf-8")
    assert "Có bao nhiêu công trình?" in raw  # không bị escape thành \u...
    turns = json.loads(raw)
    assert len(turns) == 1
    assert (turns[0]["question"], turns[0]["answer"]) == ("Có bao nhiêu công trình?", "Có 24 công trình.")
    assert turns[0]["tool_calls"] == [{"tool": "run_readonly_sql", "args": {"query": "SELECT 1"}}]
    assert datetime.fromisoformat(turns[0]["timestamp"]).tzinfo is not None


def test_turns_accumulate_in_order_and_no_temp_files_are_left(tmp_path):
    log = ChatHistoryLog(tmp_path / "s.json")

    for index in range(3):
        log.append_turn(f"câu {index}", f"đáp {index}", [])

    assert [t["question"] for t in json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))] == ["câu 0", "câu 1", "câu 2"]
    assert [p.name for p in tmp_path.iterdir()] == ["s.json"]


def test_a_corrupt_existing_file_is_replaced_instead_of_crashing_the_chat(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{không phải json", encoding="utf-8")

    ChatHistoryLog(path).append_turn("q", "a", [])

    assert len(json.loads(path.read_text(encoding="utf-8"))) == 1


def test_the_file_is_created_lazily_on_the_first_turn(tmp_path):
    ChatHistoryLog(tmp_path / "s.json")

    assert not (tmp_path / "s.json").exists()
