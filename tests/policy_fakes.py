"""Đồ giả dùng chung cho test chính sách: embedder băm từ khoá, tất định, không cần mạng hay khoá API."""
import hashlib
import math
import re
import unicodedata

from app.domains.policy.infrastructure.embedding.base import EMBEDDING_DIM

_TOKEN = re.compile(r"\W+")


def tokenize(text: str) -> list[str]:
    return [token for token in _TOKEN.split(unicodedata.normalize("NFC", text).lower()) if token]


class HashingEmbedder:
    """Mỗi từ băm (sha256, không dùng `hash` vì bị salt) vào một ô của 768 chiều kèm dấu, rồi chuẩn hoá L2.

    Hai văn bản chung từ nào thì cosine cao hơn so với văn bản không chung từ. `calls` ghi lại mọi lần gọi
    để test khẳng định "embedder không bị gọi".
    """

    model = "hashing-test"

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(("documents", list(texts)))
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self.calls.append(("query", [text]))
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIM
        for token in tokenize(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % EMBEDDING_DIM
            vector[bucket] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector
