"""Embedder: bản Gemini chạy bằng SDK thật + server Gemini giả cục bộ (không cần khoá), và bản băm cho test."""
import json
import math
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from google import genai
from google.genai import types

from app.domains.policy.infrastructure.embedding.base import (
    EMBEDDING_DIM,
    EmbeddingError,
    EmbeddingNotConfiguredError,
)
from app.domains.policy.infrastructure.embedding.gemini import GeminiEmbedder, build_embedder
from tests.policy_fakes import HashingEmbedder

API_KEY = "fake-key-do-not-leak-4242"


class _FakeEmbeddingGemini(BaseHTTPRequestHandler):
    """Trả mỗi văn bản một vector mà phần tử đầu là số đứng sau chữ `t` (để kiểm thứ tự), còn lại là 0."""

    requests: list = []
    dim = EMBEDDING_DIM
    drop_last = False
    fail_with: int | None = None

    def do_POST(self):  # noqa: N802 -- tên do http.server quy định
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        cls = type(self)
        cls.requests.append({"path": self.path, "body": body})
        if cls.fail_with:
            self._send(cls.fail_with, {"error": {"code": cls.fail_with, "message": "quota exhausted", "status": "RESOURCE_EXHAUSTED"}})
            return
        if not self.path.endswith(":batchEmbedContents"):
            self.send_error(404)
            return
        embeddings = []
        for request in body["requests"]:
            text = request["content"]["parts"][0]["text"]
            values = [0.0] * cls.dim
            values[0] = float(text[1:]) if text[1:].isdigit() else 0.0
            embeddings.append({"values": values})
        if cls.drop_last:
            embeddings.pop()
        self._send(200, {"embeddings": embeddings})

    def _send(self, status: int, payload: dict) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def log_message(self, *args):
        pass


@pytest.fixture
def fake_embedding_gemini():
    _FakeEmbeddingGemini.requests = []
    _FakeEmbeddingGemini.dim = EMBEDDING_DIM
    _FakeEmbeddingGemini.drop_last = False
    _FakeEmbeddingGemini.fail_with = None
    server = HTTPServer(("127.0.0.1", 0), _FakeEmbeddingGemini)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", _FakeEmbeddingGemini
    server.shutdown()
    server.server_close()


def _embedder(base_url: str, batch_size: int = 50) -> GeminiEmbedder:
    client = genai.Client(api_key=API_KEY, http_options=types.HttpOptions(base_url=base_url))
    return GeminiEmbedder("gemini-embedding-001", client, batch_size=batch_size)


def test_documents_are_split_into_batches_and_keep_their_order(fake_embedding_gemini):
    base_url, fake = fake_embedding_gemini
    texts = [f"t{i}" for i in range(120)]

    vectors = _embedder(base_url, batch_size=50).embed_documents(texts)

    assert len(fake.requests) == 3
    assert [len(r["body"]["requests"]) for r in fake.requests] == [50, 50, 20]
    assert [v[0] for v in vectors] == [float(i) for i in range(120)]
    assert all(len(v) == EMBEDDING_DIM for v in vectors)


def test_document_requests_use_retrieval_document_and_768_dims(fake_embedding_gemini):
    base_url, fake = fake_embedding_gemini

    _embedder(base_url).embed_documents(["t1", "t2"])

    (request,) = fake.requests
    assert request["path"].endswith("/models/gemini-embedding-001:batchEmbedContents")
    for item in request["body"]["requests"]:
        assert item["taskType"] == "RETRIEVAL_DOCUMENT"
        assert item["outputDimensionality"] == 768
        assert item["model"].endswith("gemini-embedding-001")


def test_query_request_uses_retrieval_query_and_768_dims(fake_embedding_gemini):
    base_url, fake = fake_embedding_gemini

    vector = _embedder(base_url).embed_query("t7")

    (request,) = fake.requests
    (item,) = request["body"]["requests"]
    assert item["taskType"] == "RETRIEVAL_QUERY"
    assert item["outputDimensionality"] == 768
    assert item["content"]["parts"][0]["text"] == "t7"
    assert len(vector) == EMBEDDING_DIM and vector[0] == 7.0


def test_empty_document_list_sends_no_request(fake_embedding_gemini):
    base_url, fake = fake_embedding_gemini

    assert _embedder(base_url).embed_documents([]) == []
    assert fake.requests == []


@pytest.mark.parametrize("bad", ["", "   \n"])
def test_blank_text_is_rejected_before_any_request(fake_embedding_gemini, bad):
    base_url, fake = fake_embedding_gemini
    embedder = _embedder(base_url)

    with pytest.raises(EmbeddingError):
        embedder.embed_documents(["t1", bad])
    with pytest.raises(EmbeddingError):
        embedder.embed_query(bad)
    assert fake.requests == []


def test_wrong_vector_length_from_server_is_an_error(fake_embedding_gemini):
    base_url, fake = fake_embedding_gemini
    fake.dim = 512

    with pytest.raises(EmbeddingError, match="512"):
        _embedder(base_url).embed_documents(["t1"])
    with pytest.raises(EmbeddingError):
        _embedder(base_url).embed_query("t1")


def test_wrong_number_of_vectors_from_server_is_an_error(fake_embedding_gemini):
    base_url, fake = fake_embedding_gemini
    fake.drop_last = True

    with pytest.raises(EmbeddingError):
        _embedder(base_url).embed_documents(["t1", "t2", "t3"])


def test_server_failure_is_wrapped_and_does_not_leak_the_api_key(fake_embedding_gemini):
    base_url, fake = fake_embedding_gemini
    fake.fail_with = 429

    with pytest.raises(EmbeddingError) as excinfo:
        _embedder(base_url).embed_documents(["t1"])

    assert "quota exhausted" in str(excinfo.value)
    assert API_KEY not in str(excinfo.value)
    assert excinfo.value.__cause__ is not None


def test_unreachable_server_is_wrapped():
    with pytest.raises(EmbeddingError) as excinfo:
        _embedder("http://127.0.0.1:1").embed_query("t1")

    assert str(excinfo.value) and API_KEY not in str(excinfo.value)


def test_build_embedder_requires_an_api_key():
    with pytest.raises(EmbeddingNotConfiguredError, match="GEMINI_API_KEY"):
        build_embedder("", "gemini-embedding-001")


def test_build_embedder_honours_model_and_base_url(fake_embedding_gemini):
    base_url, fake = fake_embedding_gemini

    embedder = build_embedder(API_KEY, "gemini-embedding-001", base_url)
    embedder.embed_query("t3")

    assert embedder.model == "gemini-embedding-001"
    assert len(fake.requests) == 1


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def test_hashing_embedder_is_deterministic_normalised_and_768_wide():
    embedder = HashingEmbedder()

    first = embedder.embed_query("Bảo hành lớp sơn phủ")
    second = embedder.embed_documents(["Bảo hành lớp sơn phủ"])[0]

    assert first == second and len(first) == EMBEDDING_DIM
    assert math.isclose(math.sqrt(sum(v * v for v in first)), 1.0)
    assert embedder.model == "hashing-test"


def test_hashing_embedder_ignores_case_and_unicode_form():
    embedder = HashingEmbedder()

    composed = embedder.embed_query("Bả matit")
    decomposed = embedder.embed_query("BẢ MATIT".lower().replace("ả", "ả"))

    assert composed == decomposed


def test_hashing_embedder_prefers_texts_sharing_a_rare_word():
    embedder = HashingEmbedder()
    query = embedder.embed_query("thời hạn nghiệm thu chống thấm")
    related, unrelated = embedder.embed_documents(
        [
            "Nghiệm thu hạng mục chống thấm cần biên bản và ảnh hiện trường",
            "Vệ sinh bề mặt trước khi lăn lớp sơn lót cho tường ngoại thất",
        ]
    )

    assert _cosine(query, related) > _cosine(query, unrelated)


def test_hashing_embedder_records_its_calls():
    embedder = HashingEmbedder()
    assert embedder.calls == []

    embedder.embed_documents(["a b", "c"])
    embedder.embed_query("a")

    assert embedder.calls == [("documents", ["a b", "c"]), ("query", ["a"])]
