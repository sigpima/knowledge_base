import asyncio

from app.chat.sessions import SessionStore


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def make_store(clock=None, *, ttl_seconds=60, max_sessions=10, max_turns=3):
    clock = clock or FakeClock()
    created = []

    def factory():
        service = object()
        created.append(service)
        return service

    store = SessionStore(factory, ttl_seconds=ttl_seconds, max_sessions=max_sessions, max_turns=max_turns, clock=clock)
    return store, clock, created


def test_same_id_returns_same_service():
    store, _, created = make_store()
    session_id, service = store.get_or_create(None)
    same_id, same_service = store.get_or_create(session_id)
    assert same_id == session_id
    assert same_service is service
    assert len(created) == 1


def test_unknown_id_creates_new_session_with_new_id():
    store, _, created = make_store()
    for bad_id in ("khong-ton-tai", "", None):
        session_id, _ = store.get_or_create(bad_id)
        assert session_id and session_id != bad_id
    assert len(created) == 3


def test_expired_session_is_replaced():
    store, clock, created = make_store(ttl_seconds=60)
    session_id, service = store.get_or_create(None)
    clock.advance(61)
    new_id, new_service = store.get_or_create(session_id)
    assert new_id != session_id
    assert new_service is not service
    assert len(created) == 2


def test_use_refreshes_ttl():
    store, clock, _ = make_store(ttl_seconds=60)
    session_id, service = store.get_or_create(None)
    clock.advance(40)
    store.get_or_create(session_id)
    clock.advance(40)
    same_id, same_service = store.get_or_create(session_id)
    assert same_id == session_id
    assert same_service is service


def test_oldest_session_is_evicted_when_full():
    store, _, _ = make_store(max_sessions=2)
    first_id, first = store.get_or_create(None)
    second_id, _ = store.get_or_create(None)
    third_id, _ = store.get_or_create(None)
    assert store.get_or_create(second_id)[0] == second_id
    assert store.get_or_create(third_id)[0] == third_id
    new_id, new_service = store.get_or_create(first_id)
    assert new_id != first_id
    assert new_service is not first


def test_recently_used_session_survives_eviction():
    store, _, _ = make_store(max_sessions=2)
    first_id, _ = store.get_or_create(None)
    second_id, _ = store.get_or_create(None)
    store.get_or_create(first_id)
    store.get_or_create(None)
    assert store.get_or_create(first_id)[0] == first_id
    assert store.get_or_create(second_id)[0] != second_id


def test_is_full_after_max_turns():
    store, _, _ = make_store(max_turns=2)
    session_id, _ = store.get_or_create(None)
    assert store.is_full(session_id) is False
    store.record_turn(session_id)
    assert store.is_full(session_id) is False
    store.record_turn(session_id)
    assert store.is_full(session_id) is True


def test_unknown_session_is_not_full_and_record_turn_is_noop():
    store, _, _ = make_store(max_turns=1)
    store.record_turn("khong-ton-tai")
    assert store.is_full("khong-ton-tai") is False


def test_lock_is_one_per_live_session():
    async def scenario():
        store, clock, _ = make_store(ttl_seconds=60, max_sessions=2)
        first_id, _ = store.get_or_create(None)
        second_id, _ = store.get_or_create(None)
        lock = store.lock(first_id)
        assert isinstance(lock, asyncio.Lock)
        assert store.lock(first_id) is lock
        assert store.lock(second_id) is not lock

        # Hết hạn rồi tạo lại: id mới, khóa mới.
        clock.advance(61)
        new_id, _ = store.get_or_create(first_id)
        assert new_id != first_id
        assert store.lock(new_id) is not lock

        # Bị đẩy ra do đầy: id cũ tạo lại được thì khóa phải khác.
        store2, _, _ = make_store(max_sessions=1)
        evicted_id, _ = store2.get_or_create(None)
        evicted_lock = store2.lock(evicted_id)
        store2.get_or_create(None)
        recreated_id, _ = store2.get_or_create(evicted_id)
        assert store2.lock(recreated_id) is not evicted_lock

    asyncio.run(scenario())


def test_lock_of_unknown_session_is_not_stored():
    store, _, _ = make_store()
    assert store.lock("khong-ton-tai") is not store.lock("khong-ton-tai")
