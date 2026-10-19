"""Ghi lịch sử chat ra file JSON, mỗi phiên một file (chỉ ghi, không bao giờ đọc lại cho mô hình)."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def new_session_path(log_dir: Path, now: datetime | None = None) -> Path:
    now = now or datetime.now(timezone.utc)
    return Path(log_dir) / f"chat-{now:%Y%m%d-%H%M%S}.json"


class ChatHistoryLog:
    """Danh sách các lượt hỏi–đáp của một phiên, ghi lại sau mỗi lượt (ghi file tạm rồi đổi tên nên không bao giờ dở dang)."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _read(self) -> list[dict[str, Any]]:
        try:
            turns = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        return turns if isinstance(turns, list) else []

    def append_turn(self, question: str, answer: str, tool_calls: list[dict[str, Any]]) -> None:
        turns = self._read()
        turns.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "question": question,
            "answer": answer,
            "tool_calls": tool_calls,
        })
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(f".{self.path.name}.tmp")
        temp.write_text(json.dumps(turns, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.path)
