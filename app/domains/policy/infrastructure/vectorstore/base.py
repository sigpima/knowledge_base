"""Giao thức kho vector cho tài liệu chính sách và các lỗi của nó."""
from typing import Protocol

from app.domains.policy.application.dto import PolicyPassage
from app.domains.policy.application.services.chunker import PolicyChunk
from app.domains.policy.application.services.corpus import PolicyDocument


class PolicyStoreError(RuntimeError):
    """Kho vector lỗi hoặc đầu vào không hợp lệ. Thông báo không chứa địa chỉ máy chủ, token hay đường dẫn."""


class PolicyStoreUnavailableError(PolicyStoreError):
    """Không kết nối được Milvus, hoặc collection chưa tồn tại."""


class ReadOnlyStoreError(PolicyStoreError):
    """Gọi thao tác ghi trên kho mở ở chế độ chỉ đọc."""


class PolicyStore(Protocol):
    def ensure_collection(self) -> None: ...

    def get_document_meta(self, slug: str) -> tuple[str, str] | None:
        """`(content_hash, embedding_model)` của tài liệu; `None` nếu chưa có hoặc đang nạp dở dang."""
        ...

    def replace_document(
        self, doc: PolicyDocument, model: str, chunks: list[PolicyChunk], vectors: list[list[float]]
    ) -> None: ...

    def delete_other_than(self, keep_slugs: set[str]) -> list[str]:
        """Xoá mọi tài liệu có slug ngoài `keep_slugs`; trả các slug đã xoá."""
        ...

    def search(self, vector: list[float], model: str, top_k: int, doc_type: str | None) -> list[PolicyPassage]:
        """Giảm dần theo điểm cosine; chỉ xét chunk có `embedding_model == model`."""
        ...
