"""Kho vector Milvus (pymilvus.MilvusClient) cho tài liệu chính sách."""
import math
import re
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import grpc
from pymilvus import DataType, MilvusClient
from pymilvus.exceptions import MilvusException

from app.domains.policy.application.dto import PolicyPassage
from app.domains.policy.application.services.chunker import PolicyChunk
from app.domains.policy.application.services.corpus import PolicyDocument
from app.domains.policy.infrastructure.embedding.base import EMBEDDING_DIM
from app.domains.policy.infrastructure.vectorstore.base import (
    PolicyStoreError,
    PolicyStoreUnavailableError,
    ReadOnlyStoreError,
)
from app.infrastructure.observability.logger import get_logger

logger = get_logger(__name__)

DOC_TYPES = ("technical", "warranty")
_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,99}$")  # không có nháy, gạch chéo ngược, khoảng trắng
_QUERY_LIMIT = 16384  # giới hạn `limit` của Milvus cho query; corpus chỉ vài trăm chunk
_CONNECT_TIMEOUT_SECONDS = 10.0
_UNAVAILABLE_HINTS = ("connect", "unavailable", "deadline", "timeout", "timed out", "illegal connection")

# Độ dài tối đa (max_length) của các cột VARCHAR. Milvus (máy chủ) đếm theo BYTE UTF-8, Milvus Lite đếm theo ký tự;
# store kiểm tra theo byte để hai nơi cùng chạy được. Chunk tối đa 1000 ký tự tiếng Việt <= ~3000 byte.
_VARCHAR_LIMITS = {
    "slug": 100,
    "title": 300,
    "doc_type": 20,
    "source_name": 200,
    "content_hash": 64,
    "embedding_model": 100,
    "ingest_id": 32,
    "section_path": 2048,
    "text": 8192,
}
_PASSAGE_FIELDS = ["slug", "title", "doc_type", "section_path", "text"]


def _check_slug(slug: str) -> str:
    if not isinstance(slug, str) or not _SLUG.fullmatch(slug) or len(slug) > _VARCHAR_LIMITS["slug"]:
        raise PolicyStoreError("slug tài liệu không hợp lệ")
    return slug


def _check_doc_type(doc_type: str) -> str:
    if doc_type not in DOC_TYPES:
        raise PolicyStoreError(f"doc_type không hợp lệ (cho phép: {', '.join(DOC_TYPES)})")
    return doc_type


def _check_model(model: str) -> str:
    if not isinstance(model, str) or not _MODEL.fullmatch(model):
        raise PolicyStoreError("tên model embedding không hợp lệ")
    return model


def _check_vector(vector: list[float]) -> None:
    if len(vector) != EMBEDDING_DIM:
        raise PolicyStoreError(f"vector phải có {EMBEDDING_DIM} chiều (nhận {len(vector)})")
    if not all(math.isfinite(value) for value in vector):
        raise PolicyStoreError("vector chứa giá trị không hữu hạn")


def _check_length(field: str, value: str) -> str:
    if len(value.encode("utf-8")) > _VARCHAR_LIMITS[field]:
        raise PolicyStoreError(f"trường {field} dài quá {_VARCHAR_LIMITS[field]} byte")
    return value


def _quote(value: str) -> str:
    """Chuỗi trong biểu thức lọc. Chỉ gọi với giá trị đã qua `_check_*` (không có nháy hay gạch chéo ngược)."""
    return f'"{value}"'


class MilvusPolicyStore:
    """Kho vector chính sách trên một collection Milvus.

    Metric là COSINE (index FLAT): vector thật của Gemini (768 chiều) không có độ dài 1 nên tích vô hướng
    sẽ cho điểm sai; `PolicyPassage.score` chính là độ tương đồng cosine, càng cao càng giống. Corpus chỉ vài
    trăm chunk nên quét toàn bộ (FLAT) là đủ.

    Milvus không có transaction. `replace_document` chèn bản mới (gắn `ingest_id` mới) trước, rồi mới xoá các
    dòng cũ cùng slug; nếu dừng giữa chừng thì tạm tồn tại hai bản và `get_document_meta` trả `None` để lần
    nạp sau sửa lại, không bao giờ mất cả tài liệu.

    `reconnect` (tuỳ chọn) dùng khi chưa có `client` lúc dựng (Milvus chưa chạy): mỗi thao tác thử nối lại.
    """

    def __init__(
        self,
        client: MilvusClient | None,
        collection: str,
        read_only: bool = False,
        *,
        reconnect: Callable[[], MilvusClient] | None = None,
    ) -> None:
        self._client = client
        self._collection = collection
        self._read_only = read_only
        self._reconnect = reconnect

    # ---- hạ tầng ---------------------------------------------------------------------------------------------

    @contextmanager
    def _guard(self, action: str) -> Iterator[None]:
        """Đổi mọi lỗi pymilvus/gRPC/mạng thành `PolicyStoreError`; chi tiết chỉ vào log."""
        try:
            yield
        except PolicyStoreError:
            raise
        except (MilvusException, grpc.RpcError, OSError) as exc:
            logger.warning("Milvus lỗi khi %s", action, exc_info=True)
            if _looks_unavailable(exc):
                raise PolicyStoreUnavailableError("không kết nối được kho vector Milvus") from None
            raise PolicyStoreError(f"kho vector Milvus báo lỗi khi {action}") from None

    def _conn(self) -> MilvusClient:
        if self._client is None:
            if self._reconnect is None:
                raise PolicyStoreUnavailableError("không kết nối được kho vector Milvus")
            with self._guard("kết nối"):
                self._client = self._reconnect()
        return self._client

    def _require_collection(self, client: MilvusClient) -> None:
        if not client.has_collection(self._collection):
            raise PolicyStoreUnavailableError("collection chính sách chưa tồn tại (chưa nạp tài liệu)")

    def _forbid_write(self) -> None:
        if self._read_only:
            raise ReadOnlyStoreError("kho vector đang ở chế độ chỉ đọc")

    # ---- ghi ------------------------------------------------------------------------------------------------

    def ensure_collection(self) -> None:
        self._forbid_write()
        with self._guard("tạo collection"):
            client = self._conn()
            if not client.has_collection(self._collection):
                schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=False)
                schema.add_field("chunk_id", DataType.INT64, is_primary=True, auto_id=True)
                for name, max_length in _VARCHAR_LIMITS.items():
                    schema.add_field(name, DataType.VARCHAR, max_length=max_length)
                schema.add_field("chunk_index", DataType.INT64)
                schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)
                index_params = client.prepare_index_params()
                index_params.add_index(field_name="embedding", index_type="FLAT", metric_type="COSINE")
                # Strong: đọc thấy ngay dòng vừa ghi (get_document_meta/search ngay sau replace_document).
                client.create_collection(
                    self._collection,
                    schema=schema,
                    index_params=index_params,
                    consistency_level="Strong",
                    timeout=_CONNECT_TIMEOUT_SECONDS,
                )
            else:
                client.load_collection(self._collection)

    def replace_document(
        self, doc: PolicyDocument, model: str, chunks: list[PolicyChunk], vectors: list[list[float]]
    ) -> None:
        self._forbid_write()
        slug = _check_slug(doc.front.slug)
        _check_doc_type(doc.front.doc_type)
        _check_model(model)
        if not chunks:
            raise PolicyStoreError("tài liệu không có chunk nào để lưu")
        if len(chunks) != len(vectors):
            raise PolicyStoreError("số vector không khớp số chunk")
        for vector in vectors:
            _check_vector(vector)

        ingest_id = uuid.uuid4().hex
        rows = [
            {
                "slug": slug,
                "title": _check_length("title", doc.front.title),
                "doc_type": doc.front.doc_type,
                "source_name": _check_length("source_name", doc.source_name),
                "content_hash": _check_length("content_hash", doc.content_hash),
                "embedding_model": model,
                "ingest_id": ingest_id,
                "chunk_index": chunk.index,
                "section_path": _check_length("section_path", chunk.section_path),
                "text": _check_length("text", chunk.text),
                "embedding": [float(value) for value in vector],
            }
            for chunk, vector in zip(chunks, vectors)
        ]

        with self._guard("ghi tài liệu"):
            client = self._conn()
            self._require_collection(client)
            try:
                client.insert(self._collection, rows)
            except Exception:
                self._discard_ingest(client, slug, ingest_id)
                raise
            client.delete(self._collection, filter=f"slug == {_quote(slug)} and ingest_id != {_quote(ingest_id)}")

    def _discard_ingest(self, client: MilvusClient, slug: str, ingest_id: str) -> None:
        """Chèn thất bại giữa chừng: gỡ phần đã ghi của lần này (cố gắng hết sức), bản cũ vẫn nguyên."""
        try:
            client.delete(self._collection, filter=f"slug == {_quote(slug)} and ingest_id == {_quote(ingest_id)}")
        except Exception:  # noqa: BLE001 - dọn dẹp thất bại không được che lỗi gốc
            logger.warning("Không gỡ được phần chèn dở của %s", slug, exc_info=True)

    def delete_other_than(self, keep_slugs: set[str]) -> list[str]:
        self._forbid_write()
        for slug in keep_slugs:
            _check_slug(slug)
        with self._guard("xoá tài liệu cũ"):
            client = self._conn()
            self._require_collection(client)
            rows = client.query(
                self._collection, filter='slug != ""', output_fields=["slug"], limit=_QUERY_LIMIT
            )
            removed = sorted({row["slug"] for row in rows} - keep_slugs)
            for slug in removed:
                client.delete(self._collection, filter=f"slug == {_quote(_check_slug(slug))}")
            return removed

    # ---- đọc ------------------------------------------------------------------------------------------------

    def get_document_meta(self, slug: str) -> tuple[str, str] | None:
        _check_slug(slug)
        with self._guard("đọc thông tin tài liệu"):
            client = self._conn()
            self._require_collection(client)
            rows = client.query(
                self._collection,
                filter=f"slug == {_quote(slug)}",
                output_fields=["content_hash", "embedding_model", "ingest_id"],
                limit=_QUERY_LIMIT,
            )
            if not rows or len({row["ingest_id"] for row in rows}) != 1:
                return None
            return rows[0]["content_hash"], rows[0]["embedding_model"]

    def search(self, vector: list[float], model: str, top_k: int, doc_type: str | None) -> list[PolicyPassage]:
        _check_vector(vector)
        _check_model(model)
        if top_k < 1:
            raise PolicyStoreError("top_k phải >= 1")
        conditions = [f"embedding_model == {_quote(model)}"]
        if doc_type is not None:
            conditions.append(f"doc_type == {_quote(_check_doc_type(doc_type))}")
        with self._guard("tìm kiếm"):
            client = self._conn()
            self._require_collection(client)
            hits: list[dict[str, Any]] = client.search(
                self._collection,
                data=[[float(value) for value in vector]],
                anns_field="embedding",
                filter=" and ".join(conditions),
                limit=min(top_k, _QUERY_LIMIT),
                output_fields=_PASSAGE_FIELDS,
                search_params={"metric_type": "COSINE"},
            )[0]
        # COSINE: `distance` là độ tương đồng (càng cao càng giống).
        passages = [
            PolicyPassage(score=float(hit["distance"]), **{name: hit["entity"][name] for name in _PASSAGE_FIELDS})
            for hit in hits
        ]
        return sorted(passages, key=lambda passage: passage.score, reverse=True)


def _looks_unavailable(exc: BaseException) -> bool:
    if isinstance(exc, (grpc.RpcError, OSError)):
        return True
    return getattr(exc, "code", None) == 2 or any(hint in str(exc).lower() for hint in _UNAVAILABLE_HINTS)


def build_milvus_store(uri: str, token: str, collection: str, read_only: bool = False) -> MilvusPolicyStore:
    """Dựng store từ cấu hình. Không tạo gì trên Milvus; nếu chưa kết nối được thì mỗi thao tác tự thử nối lại.

    `uri` là `http://host:port` (Milvus) hoặc đường dẫn file `.db` (Milvus Lite).
    """

    def connect() -> MilvusClient:
        return MilvusClient(uri=uri, token=token, timeout=_CONNECT_TIMEOUT_SECONDS)

    try:
        client: MilvusClient | None = connect()
    except (MilvusException, grpc.RpcError, OSError):
        logger.warning("Chưa kết nối được Milvus khi khởi tạo; sẽ thử lại ở lần gọi sau", exc_info=True)
        client = None
    return MilvusPolicyStore(client, collection, read_only, reconnect=connect)
