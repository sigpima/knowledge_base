"""Kho vector Milvus cho tài liệu chính sách, chạy trên Milvus Lite (file DB trong tiến trình)."""
import time

import pytest

from app.domains.policy.application.dto import PolicyPassage
from app.domains.policy.application.services.chunker import PolicyChunk
from app.domains.policy.application.services.corpus import PolicyDocument, PolicyFrontMatter
from app.domains.policy.infrastructure.embedding.base import EMBEDDING_DIM
from app.domains.policy.infrastructure.vectorstore.base import (
    PolicyStoreError,
    PolicyStoreUnavailableError,
    ReadOnlyStoreError,
)
from app.domains.policy.infrastructure.vectorstore.milvus_store import MilvusPolicyStore, build_milvus_store
from tests.conftest import POLICY_TEST_COLLECTION

MODEL = "model-a"


def onehot(index: int, scale: float = 1.0) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    vector[index] = scale
    return vector


def make_doc(slug="a", doc_type="technical", content_hash="hash-1", title="Tài liệu A") -> PolicyDocument:
    return PolicyDocument(
        front=PolicyFrontMatter(slug=slug, title=title, doc_type=doc_type),
        body="thân",
        source_name=f"{slug}.md",
        content_hash=content_hash,
    )


def make_chunks(count: int, prefix: str = "đoạn", title: str = "Tài liệu A") -> list[PolicyChunk]:
    return [PolicyChunk(index=i, section_path=f"{title} › Mục {i}", text=f"{prefix} {i}") for i in range(count)]


def put(store, slug="a", doc_type="technical", count=2, model=MODEL, content_hash="hash-1", prefix="đoạn", vectors=None):
    chunks = make_chunks(count, prefix=prefix)
    vectors = vectors if vectors is not None else [onehot(i) for i in range(count)]
    store.replace_document(make_doc(slug, doc_type, content_hash), model, chunks, vectors)


def raw_row(slug: str, ingest_id: str, index: int) -> dict:
    return {
        "slug": slug,
        "title": "T",
        "doc_type": "technical",
        "source_name": f"{slug}.md",
        "content_hash": "h",
        "embedding_model": MODEL,
        "ingest_id": ingest_id,
        "chunk_index": index,
        "section_path": "T",
        "text": f"dòng {ingest_id}",
        "embedding": onehot(index),
    }


def texts(passages: list[PolicyPassage]) -> list[str]:
    return [p.text for p in passages]


def test_ensure_collection_is_idempotent(policy_store):
    policy_store.ensure_collection()
    policy_store.ensure_collection()


def test_replace_then_get_document_meta(policy_store):
    put(policy_store, slug="a", content_hash="hash-1")
    assert policy_store.get_document_meta("a") == ("hash-1", MODEL)


def test_get_document_meta_unknown_slug_is_none(policy_store):
    assert policy_store.get_document_meta("khong-co") is None


def test_second_replace_keeps_only_new_version(policy_store):
    put(policy_store, count=3, prefix="cũ", content_hash="hash-1")
    put(policy_store, count=1, prefix="mới", content_hash="hash-2", vectors=[onehot(0)])

    found = policy_store.search(onehot(0), MODEL, top_k=50, doc_type=None)

    assert texts(found) == ["mới 0"]
    assert policy_store.get_document_meta("a") == ("hash-2", MODEL)


def test_replace_does_not_touch_other_slugs(policy_store):
    put(policy_store, slug="a", prefix="một")
    put(policy_store, slug="b", prefix="hai")
    put(policy_store, slug="a", prefix="ba", count=1, vectors=[onehot(0)])

    found = policy_store.search(onehot(0), MODEL, top_k=50, doc_type=None)

    assert sorted(texts(found)) == ["ba 0", "hai 0", "hai 1"]


def test_two_ingest_ids_for_one_slug_report_no_meta(policy_client, policy_store):
    policy_client.insert(POLICY_TEST_COLLECTION, [raw_row("a", "i" * 32, 0), raw_row("a", "j" * 32, 1)])

    assert policy_store.get_document_meta("a") is None


def test_replace_heals_a_half_written_document(policy_client, policy_store):
    policy_client.insert(POLICY_TEST_COLLECTION, [raw_row("a", "i" * 32, 0), raw_row("a", "j" * 32, 1)])

    put(policy_store, count=1, prefix="lành", vectors=[onehot(0)])

    assert policy_store.get_document_meta("a") == ("hash-1", MODEL)
    assert texts(policy_store.search(onehot(0), MODEL, top_k=50, doc_type=None)) == ["lành 0"]


def test_delete_other_than_removes_only_other_slugs(policy_store):
    put(policy_store, slug="a")
    put(policy_store, slug="b")
    put(policy_store, slug="c")

    removed = policy_store.delete_other_than({"a"})

    assert sorted(removed) == ["b", "c"]
    assert policy_store.get_document_meta("a") is not None
    assert policy_store.get_document_meta("b") is None
    assert policy_store.get_document_meta("c") is None
    assert policy_store.delete_other_than({"a"}) == []


def test_delete_other_than_empty_set_clears_everything(policy_store):
    put(policy_store, slug="a")
    assert policy_store.delete_other_than(set()) == ["a"]
    assert policy_store.search(onehot(0), MODEL, top_k=5, doc_type=None) == []


def test_search_orders_by_cosine_score_descending(policy_store):
    near = [1.0] + [0.1] + [0.0] * (EMBEDDING_DIM - 2)
    far = [1.0, 1.0, 1.0] + [0.0] * (EMBEDDING_DIM - 3)
    # Vector gần nhất có độ dài rất nhỏ: nếu dùng tích vô hướng thì sẽ xếp cuối, cosine thì xếp đầu.
    tiny_exact = onehot(0, scale=0.001)
    chunks = [
        PolicyChunk(0, "T", "xa"),
        PolicyChunk(1, "T", "gần"),
        PolicyChunk(2, "T", "khớp"),
    ]
    policy_store.replace_document(make_doc(), MODEL, chunks, [far, near, tiny_exact])

    found = policy_store.search(onehot(0), MODEL, top_k=10, doc_type=None)

    assert texts(found) == ["khớp", "gần", "xa"]
    scores = [p.score for p in found]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == pytest.approx(1.0, abs=1e-4)
    assert all(isinstance(p.score, float) for p in found)


def test_search_returns_full_passage(policy_store):
    policy_store.replace_document(
        make_doc(slug="bao-hanh", doc_type="warranty", title="Bảo hành"),
        MODEL,
        [PolicyChunk(0, "Bảo hành › Thời hạn", "Thời hạn bảo hành là 24 tháng.")],
        [onehot(5)],
    )

    [passage] = policy_store.search(onehot(5), MODEL, top_k=3, doc_type=None)

    assert passage == PolicyPassage(
        slug="bao-hanh",
        title="Bảo hành",
        doc_type="warranty",
        section_path="Bảo hành › Thời hạn",
        text="Thời hạn bảo hành là 24 tháng.",
        score=pytest.approx(1.0, abs=1e-4),
    )


def test_search_respects_top_k(policy_store):
    put(policy_store, count=6, vectors=[onehot(0, scale=i + 1) if i == 0 else onehot(i) for i in range(6)])

    assert len(policy_store.search(onehot(0), MODEL, top_k=3, doc_type=None)) == 3


def test_search_filters_by_doc_type(policy_store):
    put(policy_store, slug="ky-thuat", doc_type="technical", prefix="kt", count=1, vectors=[onehot(0)])
    put(policy_store, slug="bao-hanh", doc_type="warranty", prefix="bh", count=1, vectors=[onehot(0)])

    assert texts(policy_store.search(onehot(0), MODEL, top_k=10, doc_type="warranty")) == ["bh 0"]
    assert texts(policy_store.search(onehot(0), MODEL, top_k=10, doc_type="technical")) == ["kt 0"]
    assert sorted(texts(policy_store.search(onehot(0), MODEL, top_k=10, doc_type=None))) == ["bh 0", "kt 0"]


def test_search_never_returns_chunks_of_another_model(policy_store):
    put(policy_store, slug="a", model="model-a", prefix="của a", count=1, vectors=[onehot(0)])
    put(policy_store, slug="b", model="model-b", prefix="của b", count=1, vectors=[onehot(0)])

    assert texts(policy_store.search(onehot(0), "model-a", top_k=10, doc_type=None)) == ["của a 0"]
    assert texts(policy_store.search(onehot(0), "model-b", top_k=10, doc_type=None)) == ["của b 0"]
    assert policy_store.search(onehot(0), "model-chua-co", top_k=10, doc_type=None) == []


def test_vietnamese_text_at_chunk_limit_fits(policy_store):
    text = "Ướt, ẩm, ợ, ặ, ễ " * 59  # ~1000 ký tự, mỗi ký tự có dấu chiếm 2-3 byte UTF-8
    text = text[:1000]
    path = " › ".join(["Chính sách bảo hành và nghiệm thu công trình sơn"] + ["Mục con rất dài ở đây"] * 10)
    policy_store.replace_document(
        make_doc(title="Chính sách bảo hành và nghiệm thu công trình sơn"),
        MODEL,
        [PolicyChunk(0, path, text)],
        [onehot(0)],
    )

    [passage] = policy_store.search(onehot(0), MODEL, top_k=1, doc_type=None)

    assert passage.text == text
    assert passage.section_path == path


def test_wrong_vector_dimension_is_store_error(policy_store):
    with pytest.raises(PolicyStoreError):
        policy_store.replace_document(make_doc(), MODEL, make_chunks(1), [[1.0, 0.0, 0.0]])
    with pytest.raises(PolicyStoreError):
        policy_store.search([1.0, 0.0], MODEL, top_k=3, doc_type=None)


def test_replace_rejects_mismatched_or_empty_chunks(policy_store):
    put(policy_store, count=1, vectors=[onehot(0)])
    with pytest.raises(PolicyStoreError):
        policy_store.replace_document(make_doc(), MODEL, make_chunks(2), [onehot(0)])
    with pytest.raises(PolicyStoreError):
        policy_store.replace_document(make_doc(), MODEL, [], [])
    # Lỗi không làm mất bản đang có.
    assert policy_store.get_document_meta("a") == ("hash-1", MODEL)


def test_replace_rejects_oversized_fields_without_echoing_content(policy_store):
    huge = PolicyChunk(0, "T", "x" * 9000)
    with pytest.raises(PolicyStoreError) as caught:
        policy_store.replace_document(make_doc(), MODEL, [huge], [onehot(0)])
    assert "xxxx" not in str(caught.value)


def test_replace_rejects_failed_insert_but_keeps_old_version(policy_store):
    put(policy_store, count=1, prefix="cũ", vectors=[onehot(0)])
    bad = [float("nan")] + [0.0] * (EMBEDDING_DIM - 1)
    with pytest.raises(PolicyStoreError):
        policy_store.replace_document(make_doc(content_hash="hash-2"), MODEL, make_chunks(1), [bad])
    assert texts(policy_store.search(onehot(0), MODEL, top_k=10, doc_type=None)) == ["cũ 0"]


@pytest.mark.parametrize("slug", ['a"b', "a\\b", "A", "a b", "", 'x" or slug != "'])
def test_slug_is_validated_before_use_in_filters(policy_store, slug):
    with pytest.raises(PolicyStoreError):
        policy_store.get_document_meta(slug)
    doc = PolicyDocument(
        front=PolicyFrontMatter.model_construct(slug=slug, title="T", doc_type="technical", applies_to=[]),
        body="",
        source_name="x.md",
        content_hash="h",
    )
    with pytest.raises(PolicyStoreError):
        policy_store.replace_document(doc, MODEL, make_chunks(1), [onehot(0)])


def test_delete_other_than_validates_slugs(policy_store):
    with pytest.raises(PolicyStoreError):
        policy_store.delete_other_than({'a" or slug != "'})


@pytest.mark.parametrize("doc_type", ['x" or doc_type != "', "other", "", "Technical"])
def test_doc_type_is_validated(policy_store, doc_type):
    with pytest.raises(PolicyStoreError):
        policy_store.search(onehot(0), MODEL, top_k=3, doc_type=doc_type)


@pytest.mark.parametrize("model", ['m"', "m\\", 'm" or embedding_model != "', "", "m" * 101, "m\n"])
def test_model_is_validated(policy_store, model):
    with pytest.raises(PolicyStoreError):
        policy_store.search(onehot(0), model, top_k=3, doc_type=None)
    with pytest.raises(PolicyStoreError):
        policy_store.replace_document(make_doc(), model, make_chunks(1), [onehot(0)])


@pytest.mark.parametrize("top_k", [0, -1])
def test_top_k_must_be_positive(policy_store, top_k):
    with pytest.raises(PolicyStoreError):
        policy_store.search(onehot(0), MODEL, top_k=top_k, doc_type=None)


def test_read_only_store_can_search_but_not_write(policy_client, policy_store):
    put(policy_store, count=1, vectors=[onehot(0)])
    read_only = MilvusPolicyStore(policy_client, POLICY_TEST_COLLECTION, read_only=True)

    assert texts(read_only.search(onehot(0), MODEL, top_k=3, doc_type=None)) == ["đoạn 0"]
    assert read_only.get_document_meta("a") == ("hash-1", MODEL)
    with pytest.raises(ReadOnlyStoreError):
        read_only.ensure_collection()
    with pytest.raises(ReadOnlyStoreError):
        read_only.replace_document(make_doc(), MODEL, make_chunks(1), [onehot(0)])
    with pytest.raises(ReadOnlyStoreError):
        read_only.delete_other_than(set())
    assert policy_store.get_document_meta("a") is not None


def test_read_only_store_on_empty_database_is_unavailable_and_creates_nothing(tmp_path):
    from pymilvus import MilvusClient

    client = MilvusClient(str(tmp_path / "empty.db"))
    try:
        store = MilvusPolicyStore(client, "chua_co", read_only=True)
        with pytest.raises(PolicyStoreUnavailableError):
            store.search(onehot(0), MODEL, top_k=3, doc_type=None)
        with pytest.raises(PolicyStoreUnavailableError):
            store.get_document_meta("a")
        assert client.list_collections() == []
    finally:
        client.close()


def test_build_milvus_store_read_only_does_not_create_collection(tmp_path):
    path = str(tmp_path / "built.db")
    store = build_milvus_store(path, "", "chua_co", read_only=True)
    with pytest.raises(PolicyStoreUnavailableError):
        store.search(onehot(0), MODEL, top_k=3, doc_type=None)


def test_build_milvus_store_writable_round_trip(tmp_path):
    store = build_milvus_store(str(tmp_path / "built.db"), "", "chinh_sach")
    store.ensure_collection()
    put(store, count=1, vectors=[onehot(0)])
    assert texts(store.search(onehot(0), MODEL, top_k=3, doc_type=None)) == ["đoạn 0"]


def test_unreachable_server_fails_fast_without_leaking_the_address():
    started = time.monotonic()
    store = build_milvus_store("http://127.0.0.1:1", "bi-mat-token", "x", read_only=True)
    with pytest.raises(PolicyStoreUnavailableError) as caught:
        store.search(onehot(0), MODEL, top_k=3, doc_type=None)
    assert time.monotonic() - started < 10
    message = str(caught.value)
    assert "127.0.0.1" not in message
    assert "bi-mat-token" not in message


def test_unreachable_server_writer_paths_are_unavailable_too():
    store = build_milvus_store("http://127.0.0.1:1", "", "x")
    with pytest.raises(PolicyStoreUnavailableError):
        store.ensure_collection()
    with pytest.raises(PolicyStoreUnavailableError):
        store.get_document_meta("a")
    with pytest.raises(PolicyStoreUnavailableError):
        store.replace_document(make_doc(), MODEL, make_chunks(1), [onehot(0)])
    with pytest.raises(PolicyStoreUnavailableError):
        store.delete_other_than(set())


def test_failed_insert_is_store_error_and_cleans_up_partial_rows(policy_client, policy_store, caplog):
    from pymilvus.exceptions import MilvusException

    put(policy_store, count=1, prefix="cũ", vectors=[onehot(0)])

    class FlakyClient:
        """Chèn xong rồi báo lỗi, như khi mất kết nối sau khi máy chủ đã nhận dữ liệu."""

        def __init__(self, inner):
            self._inner = inner

        def insert(self, *args, **kwargs):
            self._inner.insert(*args, **kwargs)
            raise MilvusException(message="chèn lỗi giữa chừng tại 10.9.8.7")

        def __getattr__(self, name):
            return getattr(self._inner, name)

    flaky = MilvusPolicyStore(FlakyClient(policy_client), POLICY_TEST_COLLECTION)
    with pytest.raises(PolicyStoreError) as caught:
        flaky.replace_document(make_doc(content_hash="hash-2"), MODEL, make_chunks(1, prefix="mới"), [onehot(0)])

    assert "10.9.8.7" not in str(caught.value)
    assert not isinstance(caught.value, PolicyStoreUnavailableError)
    assert texts(policy_store.search(onehot(0), MODEL, top_k=10, doc_type=None)) == ["cũ 0"]
    assert policy_store.get_document_meta("a") == ("hash-1", MODEL)
