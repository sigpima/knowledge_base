"""Dịch vụ truy xuất chính sách: kiểm tra đầu vào trước, lỗi tiếng Việt không lộ bí mật, ngưỡng điểm, cache thread-safe."""
import threading
import time
import unicodedata
from pathlib import Path

import pytest

from app.domains.policy.application.dto import PolicyPassage
from app.domains.policy.application.services.corpus import load_policy_dir
from app.domains.policy.application.services.ingest import ingest_policy
from app.domains.policy.application.services.retrieval import (
    POLICY_DOC_TYPES,
    POLICY_QUERY_MAX_CHARS,
    POLICY_TOP_K_MAX,
    PolicySearchService,
)
from app.domains.policy.infrastructure.embedding.base import EmbeddingError, EmbeddingNotConfiguredError
from app.domains.policy.infrastructure.vectorstore.base import PolicyStoreError, PolicyStoreUnavailableError
from tests.policy_fakes import HashingEmbedder

CORPUS_DIR = Path(__file__).parent.parent / "data" / "policies"
SECRETS = ("http://10.9.8.7:19530", "tok-s3cret-value", "AIza-fake-key", "/var/data/secret.db")


class SpyStore:
    """Bọc store thật, ghi lại các lần gọi `search`."""

    def __init__(self, inner):
        self.inner = inner
        self.searches: list[tuple[int, str | None]] = []
        self.other_model_checks: list[str] = []

    def search(self, vector, model, top_k, doc_type):
        self.searches.append((top_k, doc_type))
        return self.inner.search(vector, model, top_k, doc_type)

    def has_other_model_rows(self, model):
        self.other_model_checks.append(model)
        return self.inner.has_other_model_rows(model)


class FixedStore:
    def __init__(self, passages, other_model_rows=False):
        self.passages = passages
        self.other_model_rows = other_model_rows
        self.other_model_checks: list[str] = []

    def search(self, vector, model, top_k, doc_type):
        return list(self.passages)

    def has_other_model_rows(self, model):
        self.other_model_checks.append(model)
        return self.other_model_rows


class FailingStore:
    def __init__(self, error):
        self.error = error

    def search(self, vector, model, top_k, doc_type):
        raise self.error

    def has_other_model_rows(self, model):
        raise self.error


class FailingEmbedder(HashingEmbedder):
    def __init__(self, error):
        super().__init__()
        self.error = error

    def embed_query(self, text):
        raise self.error


def passage(slug="a", score=0.9, doc_type="technical"):
    return PolicyPassage(slug=slug, title=f"Tiêu đề {slug}", doc_type=doc_type, section_path="Mục 1 › Mục con", text="nội dung", score=score)


@pytest.fixture
def loaded(policy_store):
    embedder = HashingEmbedder()
    for doc in load_policy_dir(CORPUS_DIR):
        ingest_policy(policy_store, embedder, doc)
    embedder.calls.clear()
    return policy_store, embedder


def make_service(loaded, **kwargs):
    store, embedder = loaded
    spy = SpyStore(store)
    return PolicySearchService(lambda: spy, lambda: embedder, **kwargs), spy, embedder


def test_constants_match_the_contract():
    assert (POLICY_QUERY_MAX_CHARS, POLICY_TOP_K_MAX, POLICY_DOC_TYPES) == (500, 8, ("technical", "warranty"))


def test_waterproofing_question_finds_the_waterproofing_procedure(loaded):
    service, _, _ = make_service(loaded)

    result = service.search("thử ngâm nước 48 giờ")

    assert "error" not in result
    assert result["passages"][0]["slug"] == "thi-cong-chong-tham"


def test_success_shape_uses_the_binding_keys_and_rounds_score(loaded):
    service, _, _ = make_service(loaded)

    result = service.search("thử ngâm nước 48 giờ", top_k=3)

    assert set(result) == {"passages", "row_count"}
    assert result["row_count"] == len(result["passages"]) == 3
    for item in result["passages"]:
        assert set(item) == {"slug", "title", "doc_type", "section", "text", "score"}
        assert item["section"] and item["text"]
        assert item["score"] == round(item["score"], 4)


def test_section_is_the_passage_section_path():
    service = PolicySearchService(lambda: FixedStore([passage(score=0.123456)]), HashingEmbedder)

    (item,) = service.search("câu hỏi")["passages"]

    assert item["section"] == "Mục 1 › Mục con"
    assert item["score"] == 0.1235


def test_doc_type_warranty_returns_only_warranty_passages(loaded):
    service, spy, _ = make_service(loaded)

    result = service.search("bảo hành chống thấm", doc_type="warranty")

    assert result["passages"] and {p["doc_type"] for p in result["passages"]} == {"warranty"}
    assert spy.searches[-1][1] == "warranty"


@pytest.mark.parametrize("query", ["", "   \n\t  ", "a" * (POLICY_QUERY_MAX_CHARS + 1)])
def test_invalid_query_is_an_error_and_nothing_is_called(query):
    embedder = HashingEmbedder()
    built = []
    service = PolicySearchService(lambda: built.append("store"), lambda: built.append("embedder") or embedder)

    result = service.search(query)

    assert set(result) == {"error"} and result["error"]
    assert embedder.calls == [] and built == []


def test_query_of_exactly_max_chars_is_accepted(loaded):
    service, _, embedder = make_service(loaded)

    result = service.search("a" * POLICY_QUERY_MAX_CHARS)

    assert "error" not in result and len(embedder.calls) == 1


def test_length_limit_is_applied_after_strip(loaded):
    service, _, _ = make_service(loaded)

    assert "error" not in service.search("  " + "a" * POLICY_QUERY_MAX_CHARS + "  ")


@pytest.mark.parametrize("top_k, expected", [(0, 1), (-5, 1), (1, 1), (5, 5), (99, POLICY_TOP_K_MAX)])
def test_top_k_is_clamped_not_an_error(loaded, top_k, expected):
    service, spy, _ = make_service(loaded)

    result = service.search("bảo hành", top_k=top_k)

    assert "error" not in result
    assert spy.searches == [(expected, None)]
    assert len(result["passages"]) <= expected


def test_unknown_doc_type_is_an_error_and_nothing_is_called():
    embedder = HashingEmbedder()
    service = PolicySearchService(lambda: FixedStore([]), lambda: embedder)

    result = service.search("bảo hành", doc_type="khac")

    assert set(result) == {"error"} and "khac" in result["error"]
    assert embedder.calls == []


def test_nfd_query_gives_the_same_result_as_nfc_and_embedder_gets_nfc(loaded):
    service, _, embedder = make_service(loaded)
    nfc = "thử ngâm nước 48 giờ"
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfd != nfc

    from_nfc = service.search(nfc)
    from_nfd = service.search(nfd)

    assert from_nfd == from_nfc
    assert [text for _, (text,) in embedder.calls] == [nfc, nfc]


def test_min_score_above_every_score_gives_empty_passages_without_error(loaded):
    service, _, _ = make_service(loaded, min_score=1.01)

    result = service.search("thử ngâm nước 48 giờ")

    assert result == {"passages": [], "row_count": 0}


def test_min_score_removes_only_the_passages_below_it():
    store = FixedStore([passage("cao", 0.9), passage("vua", 0.5), passage("thap", 0.3)])
    service = PolicySearchService(lambda: store, HashingEmbedder, min_score=0.5)

    result = service.search("câu hỏi")

    assert [p["slug"] for p in result["passages"]] == ["cao", "vua"]
    assert result["row_count"] == 2


def test_empty_store_result_is_empty_passages_not_an_error():
    service = PolicySearchService(lambda: FixedStore([]), HashingEmbedder)

    assert service.search("câu hỏi") == {"passages": [], "row_count": 0}


class OtherModelEmbedder(HashingEmbedder):
    model = "hashing-other-model"


def test_store_loaded_with_another_model_is_an_error_not_an_empty_result(loaded):
    store, _ = loaded
    embedder = OtherModelEmbedder()
    service = PolicySearchService(lambda: store, lambda: embedder)

    result = service.search("thử ngâm nước 48 giờ")

    assert set(result) == {"error"}
    assert "embedding" in result["error"] and "ingest-policies" in result["error"]
    assert "hashing" not in result["error"]
    assert len(embedder.calls) == 1


def test_same_model_with_unreachable_min_score_is_empty_without_error(loaded):
    service, spy, _ = make_service(loaded, min_score=1.01)

    assert service.search("thử ngâm nước 48 giờ") == {"passages": [], "row_count": 0}
    assert spy.other_model_checks == []  # có hit thô nên không cần kiểm tra model khác


def test_empty_real_store_is_empty_without_error(policy_store):
    policy_store.ensure_collection()
    service = PolicySearchService(lambda: policy_store, HashingEmbedder)

    assert service.search("câu hỏi") == {"passages": [], "row_count": 0}


def test_other_model_check_failure_becomes_a_store_error():
    store = FixedStore([])
    store.has_other_model_rows = lambda model: (_ for _ in ()).throw(_leaky(PolicyStoreUnavailableError))
    service = PolicySearchService(lambda: store, HashingEmbedder)

    result = service.search("câu hỏi")

    assert set(result) == {"error"} and "chưa được nạp hoặc không kết nối được" in result["error"]
    assert not any(secret in result["error"] for secret in SECRETS)


def test_fixed_store_with_other_model_rows_reports_drift():
    store = FixedStore([], other_model_rows=True)
    service = PolicySearchService(lambda: store, HashingEmbedder)

    assert "ingest-policies" in service.search("câu hỏi")["error"]
    assert store.other_model_checks == [HashingEmbedder.model]


def _leaky(error_type):
    return error_type(" ".join(SECRETS))


@pytest.mark.parametrize(
    "embedder_error, store_error, expected_phrase",
    [
        (_leaky(EmbeddingNotConfiguredError), None, "khoá Gemini"),
        (_leaky(EmbeddingError), None, "embedding"),
        (None, _leaky(PolicyStoreUnavailableError), "chưa được nạp hoặc không kết nối được"),
        (None, _leaky(PolicyStoreError), "Kho chính sách"),
        (None, _leaky(RuntimeError), "không mong đợi"),
        (_leaky(ValueError), None, "không mong đợi"),
    ],
)
def test_failures_become_vietnamese_errors_without_secrets(embedder_error, store_error, expected_phrase, caplog):
    embedder = FailingEmbedder(embedder_error) if embedder_error else HashingEmbedder()
    store = FailingStore(store_error) if store_error else FixedStore([])
    service = PolicySearchService(lambda: store, lambda: embedder)

    result = service.search("bảo hành")

    assert set(result) == {"error"}
    assert expected_phrase in result["error"]
    assert not any(secret in result["error"] for secret in SECRETS)


def test_factory_failures_are_reported_the_same_way_and_retried():
    attempts = []

    def embedder_factory():
        attempts.append(1)
        if len(attempts) == 1:
            raise EmbeddingNotConfiguredError(SECRETS[2])
        return HashingEmbedder()

    service = PolicySearchService(lambda: FixedStore([passage()]), embedder_factory)

    first = service.search("bảo hành")
    second = service.search("bảo hành")

    assert "khoá Gemini" in first["error"] and SECRETS[2] not in first["error"]
    assert second["row_count"] == 1
    assert len(attempts) == 2


def test_embedder_and_store_are_built_lazily_once_and_reused():
    built = {"store": 0, "embedder": 0}

    def store_factory():
        built["store"] += 1
        return FixedStore([passage()])

    def embedder_factory():
        built["embedder"] += 1
        return HashingEmbedder()

    service = PolicySearchService(store_factory, embedder_factory)
    assert built == {"store": 0, "embedder": 0}

    service.search("một")
    service.search("hai")

    assert built == {"store": 1, "embedder": 1}


def test_concurrent_first_calls_build_each_dependency_once():
    built = {"store": 0, "embedder": 0}

    def store_factory():
        built["store"] += 1
        time.sleep(0.05)
        return FixedStore([passage()])

    def embedder_factory():
        built["embedder"] += 1
        time.sleep(0.05)
        return HashingEmbedder()

    service = PolicySearchService(store_factory, embedder_factory)
    results = []
    threads = [threading.Thread(target=lambda: results.append(service.search("bảo hành"))) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert built == {"store": 1, "embedder": 1}
    assert [r["row_count"] for r in results] == [1] * 8
