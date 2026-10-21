"""Kho phiên hội thoại trong RAM: mỗi khách một `ChatService`, hết hạn theo TTL, giới hạn số phiên và số lượt.

Chỉ giữ đối tượng dịch vụ, bộ đếm lượt và khóa của phiên; không lưu nội dung câu hỏi của khách.
"""
import asyncio
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable

from app.chat.service import ChatService


@dataclass
class _Session:
    service: ChatService
    last_used: float
    turns: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class SessionStore:
    """`OrderedDict` xếp theo thời điểm dùng gần nhất: phần tử đầu là phiên cũ nhất.

    Không an toàn đa luồng; dùng trong một event loop duy nhất (các phương thức đều đồng bộ, không `await`).
    """

    def __init__(
        self,
        factory: Callable[[], ChatService],
        *,
        ttl_seconds: int,
        max_sessions: int,
        max_turns: int,
        clock: Callable[[], float] = time.monotonic,
    ):
        if max_sessions < 1:
            raise ValueError("max_sessions phải >= 1")
        self._factory = factory
        self._ttl_seconds = ttl_seconds
        self._max_sessions = max_sessions
        self._max_turns = max_turns
        self._clock = clock
        self._sessions: OrderedDict[str, _Session] = OrderedDict()

    def _purge_expired(self, now: float) -> None:
        # Thứ tự dùng gần nhất tăng dần nên chỉ cần xét từ đầu cho đến phiên còn hạn đầu tiên.
        while self._sessions:
            oldest_id, oldest = next(iter(self._sessions.items()))
            if now - oldest.last_used <= self._ttl_seconds:
                break
            del self._sessions[oldest_id]

    def get_or_create(self, session_id: str | None) -> tuple[str, ChatService]:
        """Trả phiên của `session_id`; id lạ, rỗng hoặc đã hết hạn thì tạo phiên mới với id mới."""
        now = self._clock()
        self._purge_expired(now)
        session = self._sessions.get(session_id) if session_id else None
        if session is not None:
            session.last_used = now
            self._sessions.move_to_end(session_id)
            return session_id, session.service
        while len(self._sessions) >= self._max_sessions:
            self._sessions.popitem(last=False)
        new_id = secrets.token_urlsafe(16)
        session = _Session(service=self._factory(), last_used=now)
        self._sessions[new_id] = session
        return new_id, session.service

    def _live(self, session_id: str) -> _Session | None:
        """Phiên còn hạn của `session_id` (sau khi dọn phiên hết hạn), hoặc None."""
        self._purge_expired(self._clock())
        return self._sessions.get(session_id)

    def record_turn(self, session_id: str) -> None:
        """Cộng một lượt và coi như phiên vừa được dùng (làm mới TTL, đưa về cuối hàng đợi đẩy ra).

        Phiên đang chạy lâu nhờ vậy không bị đẩy ra khi lượt kết thúc. Bỏ qua nếu phiên không còn.
        """
        session = self._live(session_id)
        if session is not None:
            session.turns += 1
            session.last_used = self._clock()
            self._sessions.move_to_end(session_id)

    def is_full(self, session_id: str) -> bool:
        """Phiên đã dùng đủ số lượt tối đa; phiên không tồn tại thì chưa đầy."""
        session = self._live(session_id)
        return session is not None and session.turns >= self._max_turns

    def lock(self, session_id: str) -> asyncio.Lock:
        """Khóa duy nhất của phiên đang sống để tuần tự hóa các yêu cầu cùng phiên.

        Khóa sinh cùng phiên và mất cùng phiên (hết hạn, bị đẩy ra). Id không tồn tại hoặc đã hết hạn thì
        ném `KeyError` (không trả khóa tạm, tránh mất tuần tự hóa một cách âm thầm). Người gọi phải gọi
        `get_or_create` rồi `lock` liền nhau, đồng bộ, không có `await` ở giữa.
        """
        session = self._live(session_id)
        if session is None:
            raise KeyError(session_id)
        return session.lock
