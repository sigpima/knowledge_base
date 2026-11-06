"""Nạp tài liệu chính sách vào kho vector: idempotent, embedding trước khi ghi."""
from pathlib import Path

import pytest

from app.domains.policy.application.services.chunker import chunk_document
from app.domains.policy.application.services.corpus import PolicyDocument, PolicyFrontMatter, load_policy_dir
from app.domains.policy.application.services.ingest import PolicyIngestResult, ingest_policy, prune_policies
from app.domains.policy.infrastructure.embedding.base import EmbeddingError
from tests.policy_fakes import HashingEmbedder

CORPUS_DIR = Path(__file__).parent.parent / "data" / "policies"

BODY = """# Quy trình thử

## Chuẩn bị bề mặt

Làm sạch bụi và dầu mỡ trước khi sơn lớp lót.

## Nghiệm thu

Kiểm tra độ dày màng sơn khô bằng thiết bị đo.
"""


def make_doc(slug="quy-trinh-thu", body=BODY, content_hash="hash-1") -> PolicyDocument:
    return PolicyDocument(
        front=PolicyFrontMatter(slug=slug, title="Quy trình thử", doc_type="technical"),
        body=body,
        source_name=f"{slug}.md",
        content_hash=content_hash,
    )


def search(store, embedder, query, top_k=20):
    return store.search(embedder.embed_query(query), embedder.model, top_k, None)


class ExplodingEmbedder(HashingEmbedder):
    def embed_documents(self, texts):
        raise EmbeddingError("hết hạn mức")


class ShortEmbedder(HashingEmbedder):
    def embed_documents(self, texts):
        return super().embed_documents(texts)[:-1]


def test_first_ingest_is_created_with_chunk_count(policy_store):
    doc = make_doc()
    embedder = HashingEmbedder()

    result = ingest_policy(policy_store, embedder, doc)

    assert result == PolicyIngestResult(slug=doc.front.slug, status="created", chunks=len(chunk_document(doc)))
    assert result.chunks > 0
    assert policy_store.get_document_meta(doc.front.slug) == (doc.content_hash, embedder.model)
    assert [text for kind, texts in embedder.calls if kind == "documents" for text in texts] == [
        chunk.embed_text for chunk in chunk_document(doc)
    ]


def test_same_document_again_is_unchanged_and_embedder_not_called(policy_store):
    doc = make_doc()
    ingest_policy(policy_store, HashingEmbedder(), doc)
    embedder = HashingEmbedder()

    result = ingest_policy(policy_store, embedder, doc)

    assert result.status == "unchanged"
    assert result.chunks == len(chunk_document(doc))
    assert embedder.calls == []


def test_changed_body_is_updated_and_old_chunks_are_gone(policy_store):
    embedder = HashingEmbedder()
    ingest_policy(policy_store, embedder, make_doc())
    assert any("dầu mỡ" in p.text for p in search(policy_store, embedder, "dầu mỡ"))

    new_doc = make_doc(body=BODY.replace("dầu mỡ", "muội than"), content_hash="hash-2")
    result = ingest_policy(policy_store, embedder, new_doc)

    assert result.status == "updated"
    texts = [p.text for p in search(policy_store, embedder, "muội than dầu mỡ")]
    assert any("muội than" in text for text in texts)
    assert not any("dầu mỡ" in text for text in texts)
    assert len(texts) == result.chunks


def test_different_embedder_model_reingests_same_content(policy_store):
    doc = make_doc()
    ingest_policy(policy_store, HashingEmbedder(), doc)
    other = HashingEmbedder()
    other.model = "hashing-test-2"

    result = ingest_policy(policy_store, other, doc)

    assert result.status == "updated"
    assert len(other.calls) == 1
    assert policy_store.get_document_meta(doc.front.slug) == (doc.content_hash, "hashing-test-2")


def test_embedding_error_propagates_and_old_document_stays(policy_store):
    embedder = HashingEmbedder()
    ingest_policy(policy_store, embedder, make_doc())
    before = [p.text for p in search(policy_store, embedder, "dầu mỡ")]

    with pytest.raises(EmbeddingError):
        ingest_policy(policy_store, ExplodingEmbedder(), make_doc(body=BODY + "\nThêm dòng.", content_hash="hash-2"))

    assert policy_store.get_document_meta("quy-trinh-thu") == ("hash-1", embedder.model)
    assert [p.text for p in search(policy_store, embedder, "dầu mỡ")] == before


def test_first_ingest_with_embedding_error_writes_nothing(policy_store):
    with pytest.raises(EmbeddingError):
        ingest_policy(policy_store, ExplodingEmbedder(), make_doc())

    assert policy_store.get_document_meta("quy-trinh-thu") is None


def test_vector_count_mismatch_raises_embedding_error_before_write(policy_store):
    with pytest.raises(EmbeddingError):
        ingest_policy(policy_store, ShortEmbedder(), make_doc())

    assert policy_store.get_document_meta("quy-trinh-thu") is None


def test_prune_removes_only_extra_slugs(policy_store):
    embedder = HashingEmbedder()
    for slug in ("giu-lai", "xoa-di", "xoa-nua"):
        ingest_policy(policy_store, embedder, make_doc(slug=slug))

    removed = prune_policies(policy_store, {"giu-lai"})

    assert removed == ["xoa-di", "xoa-nua"]
    assert policy_store.get_document_meta("giu-lai") is not None
    assert policy_store.get_document_meta("xoa-di") is None
    assert policy_store.get_document_meta("xoa-nua") is None


def test_real_corpus_ingests_idempotently(policy_store):
    documents = load_policy_dir(CORPUS_DIR)
    embedder = HashingEmbedder()

    first = [ingest_policy(policy_store, embedder, doc) for doc in documents]

    assert len(first) == 12
    assert {r.status for r in first} == {"created"}
    assert 30 <= sum(r.chunks for r in first) <= 400

    calls_before = len(embedder.calls)
    second = [ingest_policy(policy_store, embedder, doc) for doc in documents]

    assert {r.status for r in second} == {"unchanged"}
    assert [r.chunks for r in second] == [r.chunks for r in first]
    assert len(embedder.calls) == calls_before
