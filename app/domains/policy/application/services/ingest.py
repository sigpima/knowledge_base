"""Nạp tài liệu chính sách vào kho vector: bỏ qua nếu không đổi, embedding xong mới ghi."""
from dataclasses import dataclass
from typing import Literal

from app.domains.policy.application.services.chunker import chunk_document
from app.domains.policy.application.services.corpus import PolicyDocument
from app.domains.policy.infrastructure.embedding.base import Embedder, EmbeddingError
from app.domains.policy.infrastructure.vectorstore.base import PolicyStore


@dataclass(frozen=True)
class PolicyIngestResult:
    slug: str
    status: Literal["created", "updated", "unchanged"]
    chunks: int


def ingest_policy(store: PolicyStore, embedder: Embedder, doc: PolicyDocument) -> PolicyIngestResult:
    """Nạp một tài liệu. `unchanged` khi nội dung và model embedding đều trùng bản đang lưu.

    Embedding chạy trước khi ghi nên nếu nó lỗi (ngoại lệ lan ra) thì bản cũ trong kho còn nguyên.
    """
    slug = doc.front.slug
    chunks = chunk_document(doc)
    existing = store.get_document_meta(slug)
    if existing == (doc.content_hash, embedder.model):
        return PolicyIngestResult(slug=slug, status="unchanged", chunks=len(chunks))

    vectors = embedder.embed_documents([chunk.embed_text for chunk in chunks])
    if len(vectors) != len(chunks):
        raise EmbeddingError(f"Embedder trả {len(vectors)} vector cho {len(chunks)} chunk")
    store.replace_document(doc, embedder.model, chunks, vectors)
    return PolicyIngestResult(slug=slug, status="created" if existing is None else "updated", chunks=len(chunks))


def prune_policies(store: PolicyStore, keep_slugs: set[str]) -> list[str]:
    """Xoá tài liệu không còn trong nguồn; trả các slug đã xoá."""
    return store.delete_other_than(keep_slugs)
