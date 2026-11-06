"""Embedder dùng Gemini (SDK google-genai, gọi đồng bộ `models.embed_content`)."""
from google import genai
from google.genai import types

from app.domains.policy.infrastructure.embedding.base import (
    EMBEDDING_DIM,
    Embedder,
    EmbeddingError,
    EmbeddingNotConfiguredError,
)

DOCUMENT_TASK = "RETRIEVAL_DOCUMENT"
QUERY_TASK = "RETRIEVAL_QUERY"


class GeminiEmbedder:
    """Văn bản rỗng bị từ chối trước khi gửi (API không nhận); chunk từ bộ cắt luôn có nội dung."""

    def __init__(self, model: str, client: genai.Client, batch_size: int = 50) -> None:
        if batch_size < 1:
            raise ValueError("batch_size phải >= 1")
        self.model = model
        self._client = client
        self._batch_size = batch_size

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self._require_text(texts)
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            vectors.extend(self._embed(texts[start : start + self._batch_size], DOCUMENT_TASK))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        self._require_text([text])
        return self._embed([text], QUERY_TASK)[0]

    @staticmethod
    def _require_text(texts: list[str]) -> None:
        if any(not text.strip() for text in texts):
            raise EmbeddingError("Không embed được văn bản rỗng")

    def _embed(self, batch: list[str], task_type: str) -> list[list[float]]:
        config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=EMBEDDING_DIM)
        try:
            response = self._client.models.embed_content(model=self.model, contents=batch, config=config)
            vectors = [list(item.values) for item in (response.embeddings or [])]
        except Exception as exc:  # SDK/mạng/hạn mức: gói lại, chuỗi lỗi của SDK không chứa khoá API
            raise EmbeddingError(str(exc) or type(exc).__name__) from exc
        if len(vectors) != len(batch):
            raise EmbeddingError(f"Gemini trả {len(vectors)} vector cho {len(batch)} văn bản")
        for vector in vectors:
            if len(vector) != EMBEDDING_DIM:
                raise EmbeddingError(f"Vector có {len(vector)} chiều, cần {EMBEDDING_DIM}")
        return vectors


def build_embedder(api_key: str, model: str, base_url: str = "") -> Embedder:
    if not api_key:
        raise EmbeddingNotConfiguredError("Chưa có GEMINI_API_KEY")
    options = types.HttpOptions(base_url=base_url) if base_url else None
    return GeminiEmbedder(model, genai.Client(api_key=api_key, http_options=options))
