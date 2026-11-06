"""Truy xuất đoạn tài liệu chính sách cho tool MCP `search_policies`.

Mọi lỗi (đầu vào sai, chưa có khoá, Milvus chưa chạy...) trả về `{"error": "<tiếng Việt>"}` thay vì ném ngoại lệ;
chi tiết kỹ thuật chỉ vào log, thông báo không bao giờ chứa địa chỉ máy chủ, token, khoá API hay đường dẫn file.
"""
import threading
import unicodedata
from collections.abc import Callable
from typing import Any

from app.domains.policy.infrastructure.embedding.base import Embedder, EmbeddingError, EmbeddingNotConfiguredError
from app.domains.policy.infrastructure.vectorstore.base import PolicyStore, PolicyStoreError, PolicyStoreUnavailableError
from app.infrastructure.observability.logger import get_logger

logger = get_logger(__name__)

POLICY_QUERY_MAX_CHARS = 500
POLICY_TOP_K_MAX = 8
POLICY_DOC_TYPES = ("technical", "warranty")

_ERR_EMPTY_QUERY = "Câu hỏi không được để trống."
_ERR_QUERY_TOO_LONG = f"Câu hỏi quá dài (tối đa {POLICY_QUERY_MAX_CHARS} ký tự)."
_ERR_NOT_CONFIGURED = "Chưa cấu hình khoá Gemini (GEMINI_API_KEY) nên không tạo được embedding cho câu hỏi."
_ERR_EMBEDDING = "Không tạo được embedding cho câu hỏi lúc này. Hãy thử lại sau."
_ERR_STORE_UNAVAILABLE = "Kho chính sách chưa được nạp hoặc không kết nối được."
_ERR_STORE = "Kho chính sách báo lỗi khi tìm kiếm. Hãy thử lại sau."
_ERR_MODEL_DRIFT = (
    "Kho chính sách được nạp bằng model embedding khác với model đang dùng để tìm kiếm, nên không tìm được đoạn nào. "
    "Cần chạy lại ingest-policies (nạp lại tài liệu) với đúng model đang cấu hình."
)
_ERR_MISSING_PACKAGE = "Máy chủ thiếu gói cần thiết cho tìm kiếm chính sách; xem docs/rag.md."
_ERR_UNEXPECTED = "Tìm kiếm chính sách gặp lỗi không mong đợi."


class PolicySearchService:
    """Embed câu hỏi rồi tìm đoạn gần nhất trong kho vector.

    `store_factory`/`embedder_factory` được gọi lười ở lần tìm kiếm đầu và kết quả được giữ lại (có khoá, vì tool MCP
    có thể được gọi từ nhiều luồng); factory ném lỗi thì không cache gì và lần sau thử lại. Nhờ vậy dựng service
    không cần Milvus hay khoá Gemini.
    """

    def __init__(
        self,
        store_factory: Callable[[], PolicyStore],
        embedder_factory: Callable[[], Embedder],
        min_score: float = 0.0,
    ) -> None:
        self._store_factory = store_factory
        self._embedder_factory = embedder_factory
        self._min_score = min_score
        self._lock = threading.Lock()
        self._store: PolicyStore | None = None
        self._embedder: Embedder | None = None

    def search(self, query: str, top_k: int = 5, doc_type: str | None = None) -> dict[str, Any]:
        # Kiểm tra đầu vào trước mọi thứ khác: câu hỏi sai không được chạm embedder hay kho vector.
        text = unicodedata.normalize("NFC", query).strip()
        if not text:
            return {"error": _ERR_EMPTY_QUERY}
        if len(text) > POLICY_QUERY_MAX_CHARS:
            return {"error": _ERR_QUERY_TOO_LONG}
        if doc_type is not None and doc_type not in POLICY_DOC_TYPES:
            accepted = ", ".join(f"'{name}'" for name in POLICY_DOC_TYPES)
            return {"error": f"doc_type không hợp lệ: {doc_type!r}. Chỉ chấp nhận {accepted} hoặc bỏ trống."}
        top_k = max(1, min(top_k, POLICY_TOP_K_MAX))

        try:
            embedder = self._get_embedder()
            vector = embedder.embed_query(text)
            store = self._get_store()
            passages = store.search(vector, embedder.model, top_k, doc_type)
            # Không có hit nào: phân biệt "kho nạp bằng model khác" (lỗi cấu hình) với "không có đáp án" (kết quả rỗng).
            if not passages and store.has_other_model_rows(embedder.model):
                logger.warning("Kho chính sách chỉ có dòng nhúng bằng model khác model đang dùng để tìm kiếm")
                return {"error": _ERR_MODEL_DRIFT}
        except EmbeddingNotConfiguredError:
            logger.warning("Chưa cấu hình embedding cho search_policies", exc_info=True)
            return {"error": _ERR_NOT_CONFIGURED}
        except EmbeddingError:
            logger.warning("Embedding câu hỏi chính sách thất bại", exc_info=True)
            return {"error": _ERR_EMBEDDING}
        except PolicyStoreUnavailableError:
            logger.warning("Kho chính sách không dùng được", exc_info=True)
            return {"error": _ERR_STORE_UNAVAILABLE}
        except PolicyStoreError:
            logger.warning("Kho chính sách lỗi khi tìm kiếm", exc_info=True)
            return {"error": _ERR_STORE}
        except ImportError:
            logger.warning("Thiếu gói cho search_policies", exc_info=True)
            return {"error": _ERR_MISSING_PACKAGE}
        except Exception:  # noqa: BLE001 - biên của tool: lỗi lạ phải thành thông báo chung, không làm sập phiên MCP
            logger.warning("search_policies gặp lỗi không mong đợi", exc_info=True)
            return {"error": _ERR_UNEXPECTED}

        kept = [passage for passage in passages if passage.score >= self._min_score]
        return {
            "passages": [
                {
                    "slug": passage.slug,
                    "title": passage.title,
                    "doc_type": passage.doc_type,
                    "section": passage.section_path,
                    "text": passage.text,
                    "score": round(passage.score, 4),
                }
                for passage in kept
            ],
            "row_count": len(kept),
        }

    def _get_embedder(self) -> Embedder:
        with self._lock:
            if self._embedder is None:
                self._embedder = self._embedder_factory()
            return self._embedder

    def _get_store(self) -> PolicyStore:
        with self._lock:
            if self._store is None:
                self._store = self._store_factory()
            return self._store
