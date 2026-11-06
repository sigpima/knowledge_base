"""DTO của tìm kiếm tài liệu chính sách."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyPassage:
    """Một đoạn tài liệu trả về từ tìm kiếm; `score` là độ tương đồng cosine (càng cao càng giống)."""

    slug: str
    title: str
    doc_type: str
    section_path: str
    text: str
    score: float
