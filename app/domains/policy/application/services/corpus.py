"""Đọc corpus chính sách: file Markdown có front matter YAML, kiểm tra và băm nội dung."""
import hashlib
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

_FENCE = "---"


class PolicyFileError(ValueError):
    """File chính sách không hợp lệ; `errors` là danh sách thông báo (kèm tên file)."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


class PolicyFrontMatter(BaseModel):
    """Front matter của một tài liệu chính sách; cấm trường lạ."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    title: str
    doc_type: Literal["technical", "warranty"]
    applies_to: list[str] = []

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title không được rỗng")
        return value


@dataclass(frozen=True)
class PolicyDocument:
    front: PolicyFrontMatter
    body: str
    source_name: str
    content_hash: str


def _split_front_matter(text: str) -> tuple[str, str] | None:
    """Tách `---\\n<yaml>\\n---\\n<thân>`; trả None nếu không có front matter hoàn chỉnh."""
    lines = text.split("\n")
    if not lines or lines[0].rstrip() != _FENCE:
        return None
    for index in range(1, len(lines)):
        if lines[index].rstrip() == _FENCE:
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1:])
    return None


def _format_validation_errors(error: ValidationError) -> list[str]:
    messages = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"]) or "front matter"
        messages.append(f"{location}: {item['msg']}")
    return messages


def load_policy_file(path: Path) -> PolicyDocument:
    name = path.name
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PolicyFileError([f"{name}: không đọc được file ({exc})"]) from exc

    text = unicodedata.normalize("NFC", raw.removeprefix("﻿").replace("\r\n", "\n"))
    parts = _split_front_matter(text)
    if parts is None:
        raise PolicyFileError([f"{name}: thiếu front matter (file phải bắt đầu bằng dòng '---' và có dòng '---' đóng)"])
    front_text, body = parts

    try:
        data: Any = yaml.safe_load(front_text)
    except yaml.YAMLError as exc:
        raise PolicyFileError([f"{name}: front matter không phải YAML hợp lệ ({exc})"]) from exc
    if not isinstance(data, dict):
        raise PolicyFileError([f"{name}: front matter phải là một mapping khoá: giá trị"])

    try:
        front = PolicyFrontMatter.model_validate(data)
    except ValidationError as exc:
        raise PolicyFileError([f"{name}: {message}" for message in _format_validation_errors(exc)]) from exc

    return PolicyDocument(
        front=front,
        body=body.strip(),
        source_name=name,
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def load_policy_dir(path: Path) -> list[PolicyDocument]:
    documents = [load_policy_file(file) for file in sorted(path.glob("*.md"), key=lambda p: p.name)]
    first_seen: dict[str, str] = {}
    errors = []
    for document in documents:
        slug = document.front.slug
        if slug in first_seen:
            errors.append(f"slug {slug!r} bị trùng giữa {first_seen[slug]} và {document.source_name}")
        else:
            first_seen[slug] = document.source_name
    if errors:
        raise PolicyFileError(errors)
    return documents
