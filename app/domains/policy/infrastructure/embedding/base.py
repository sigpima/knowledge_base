"""Giao thức embedder cho tài liệu chính sách: biến văn bản thành vector cố định 768 chiều."""
from typing import Protocol

EMBEDDING_DIM = 768


class EmbeddingNotConfiguredError(RuntimeError):
    """Chưa cấu hình dịch vụ embedding (thiếu khoá API)."""


class EmbeddingError(RuntimeError):
    """Gọi embedding thất bại (mạng, hạn mức, phản hồi sai hình dạng...). Thông báo không chứa khoá API."""


class Embedder(Protocol):
    model: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Một vector cho mỗi văn bản, đúng thứ tự đầu vào. Danh sách rỗng trả `[]`."""
        ...

    def embed_query(self, text: str) -> list[float]: ...
