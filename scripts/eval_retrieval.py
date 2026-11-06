"""Đo chất lượng truy xuất của `search_policies` bằng bộ câu hỏi `data/policy_eval.yaml`.

    python -m scripts.eval_retrieval [--top-k 5] [--eval data/policy_eval.yaml]

Cần GEMINI_API_KEY (nhúng câu hỏi) và Milvus đã nạp tài liệu (`python -m app.cli ingest-policies data/policies`).
Chỉ ĐỌC kho; không ghi gì. Kho được mở chỉ đọc và ngưỡng điểm đặt 0 để điểm không bị lọc khi đo.

Số đo (xem docs/rag.md, mục "Đánh giá truy xuất"):
  - recall@k mức tài liệu: câu một nguồn trúng ở hạng r nếu đoạn thứ r thuộc đúng slug; câu hai nguồn chỉ trúng ở k khi
    MỌI slug mong đợi đều xuất hiện trong k đoạn đầu. recall@k mức mục: như trên nhưng đoạn còn phải thuộc đúng mục `##`.
  - MRR: nghịch đảo hạng của đoạn đầu tiên thuộc slug mong đợi (câu hai nguồn: hạng nơi slug cuối cùng xuất hiện lần đầu;
    0 nếu thiếu trong top-k).
  - Câu ngoài phạm vi (`expect: null`): ghi lại điểm của đoạn hạng 1, để so với điểm hạng 1 của câu trong phạm vi và chọn
    POLICY_MIN_SCORE.

Mã thoát: 0 chạy xong; 2 thiếu khoá Gemini, Milvus không kết nối được hoặc trống, hoặc file câu hỏi không hợp lệ.
`evaluate()` là hàm thuần (nhận hàm `search`), nên kiểm thử được mà không cần khoá hay Milvus.
"""
import argparse
import statistics
import sys
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.infrastructure.config.config import settings

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVAL_PATH = ROOT / "data" / "policy_eval.yaml"
BASE_CUTOFFS = (1, 3, 5)
MAX_TOP_K = 8  # trùng POLICY_TOP_K_MAX của dịch vụ truy xuất
MISS_TOP_SHOWN = 3
SECTION_SEPARATOR = " › "

SearchFn = Callable[[str, int], list[dict[str, Any]]]


# --------------------------------------------------------------------------------------------- file câu hỏi

class EvalSetError(ValueError):
    """File câu hỏi không đọc được hoặc sai cấu trúc; thông báo tiếng Việt, không chứa bí mật."""


class SearchFailed(RuntimeError):
    """Truy xuất không chạy được (thiếu khoá, Milvus lỗi...); `args[0]` là thông báo tiếng Việt an toàn để in."""


@dataclass(frozen=True)
class Expectation:
    slug: str
    section: str


@dataclass(frozen=True)
class EvalItem:
    question: str
    expect: tuple[Expectation, ...]  # rỗng = ngoài phạm vi

    @property
    def in_scope(self) -> bool:
        return bool(self.expect)


class _ExpectationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1)
    section: str = Field(min_length=1)


class _ItemModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    expect: _ExpectationModel | list[_ExpectationModel] | None

    @field_validator("question")
    @classmethod
    def _question_not_blank(cls, value: str) -> str:
        value = unicodedata.normalize("NFC", value).strip()
        if not value:
            raise ValueError("question không được rỗng")
        return value

    @model_validator(mode="after")
    def _multi_source_needs_distinct_documents(self) -> "_ItemModel":
        if isinstance(self.expect, list):
            if len(self.expect) < 2:
                raise ValueError("expect dạng danh sách phải có ít nhất 2 phần tử (câu một nguồn dùng mapping)")
            slugs = [entry.slug for entry in self.expect]
            if len(set(slugs)) != len(slugs):
                raise ValueError("expect dạng danh sách phải trỏ tới các tài liệu (slug) khác nhau")
        return self


def _expectations(model: _ItemModel) -> tuple[Expectation, ...]:
    entries = [] if model.expect is None else model.expect if isinstance(model.expect, list) else [model.expect]
    return tuple(
        Expectation(unicodedata.normalize("NFC", e.slug).strip(), unicodedata.normalize("NFC", e.section).strip())
        for e in entries
    )


def load_eval_set(path: Path) -> list[EvalItem]:
    name = Path(path).name
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise EvalSetError(f"{name}: không đọc được file câu hỏi") from exc
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise EvalSetError(f"{name}: không phải YAML hợp lệ") from exc
    if not isinstance(data, list) or not data:
        raise EvalSetError(f"{name}: phải là một danh sách không rỗng các câu hỏi")

    items: list[EvalItem] = []
    errors: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(data, start=1):
        try:
            model = _ItemModel.model_validate(entry)
        except ValidationError as exc:
            for problem in exc.errors():
                location = ".".join(str(part) for part in problem["loc"])
                errors.append(f"câu {index}: {location}: {problem['msg']}")
            continue
        key = " ".join(model.question.casefold().split())
        if key in seen:
            errors.append(f"câu {index}: trùng câu hỏi {model.question!r}")
            continue
        seen.add(key)
        items.append(EvalItem(model.question, _expectations(model)))
    if errors:
        raise EvalSetError(f"{name}: " + "; ".join(errors))
    return items


# --------------------------------------------------------------------------------------------- đo

@dataclass(frozen=True)
class Miss:
    """Câu trong phạm vi không trúng ở hạng 1 (câu hai nguồn: không đủ mọi slug trong top-k)."""

    question: str
    expected: tuple[Expectation, ...]
    top: tuple[tuple[str, str, float], ...]  # (slug, section, score) của vài đoạn đầu


@dataclass(frozen=True)
class EvalReport:
    top_k: int
    cutoffs: tuple[int, ...]
    single_count: int
    multi_count: int
    out_of_scope_count: int
    recall_doc: dict[int, float]
    recall_section: dict[int, float]
    mrr: float
    in_scope_top1: tuple[float, ...]
    out_of_scope_top1: tuple[float, ...]
    misses: tuple[Miss, ...]
    no_result_count: int  # số câu mà truy xuất không trả đoạn nào

    @property
    def in_scope_count(self) -> int:
        return self.single_count + self.multi_count

    @property
    def total_count(self) -> int:
        return self.in_scope_count + self.out_of_scope_count

    @property
    def in_scope_min(self) -> float | None:
        return min(self.in_scope_top1) if self.in_scope_top1 else None

    @property
    def in_scope_median(self) -> float | None:
        return statistics.median(self.in_scope_top1) if self.in_scope_top1 else None

    @property
    def out_of_scope_max(self) -> float | None:
        return max(self.out_of_scope_top1) if self.out_of_scope_top1 else None

    @property
    def out_of_scope_median(self) -> float | None:
        return statistics.median(self.out_of_scope_top1) if self.out_of_scope_top1 else None

    @property
    def groups_overlap(self) -> bool | None:
        """None nếu thiếu số liệu của một nhóm; True nếu điểm cao nhất ngoài phạm vi không thấp hơn điểm thấp nhất trong phạm vi."""
        if self.in_scope_min is None or self.out_of_scope_max is None:
            return None
        return self.out_of_scope_max >= self.in_scope_min

    @property
    def suggested_min_score(self) -> float | None:
        if self.groups_overlap is not False:
            return None
        return (self.out_of_scope_max + self.in_scope_min) / 2


def _section_matches(section: str, expected: str) -> bool:
    section = unicodedata.normalize("NFC", section)
    return section == expected or section.endswith(SECTION_SEPARATOR + expected)


def _first_rank(passages: Sequence[dict[str, Any]], expectation: Expectation, with_section: bool) -> int | None:
    for rank, passage in enumerate(passages, start=1):
        if passage.get("slug") != expectation.slug:
            continue
        if with_section and not _section_matches(str(passage.get("section", "")), expectation.section):
            continue
        return rank
    return None


def _worst_rank(passages: Sequence[dict[str, Any]], item: EvalItem, with_section: bool) -> int | None:
    """Hạng mà mọi mong đợi của câu đã xuất hiện (hạng lớn nhất trong các hạng đầu tiên); None nếu có mong đợi vắng mặt."""
    ranks = [_first_rank(passages, expectation, with_section) for expectation in item.expect]
    return None if any(rank is None for rank in ranks) else max(ranks)


def _ratio(count: int, total: int) -> float:
    return count / total if total else 0.0


def evaluate(search: SearchFn, questions: Sequence[EvalItem], top_k: int = 5) -> EvalReport:
    """Chạy `search(câu_hỏi, top_k)` cho từng câu và tính số đo. Chỉ xét `top_k` đoạn đầu mỗi lần trả về."""
    cutoffs = tuple(sorted({k for k in BASE_CUTOFFS if k <= top_k} | {top_k}))
    doc_hits = dict.fromkeys(cutoffs, 0)
    section_hits = dict.fromkeys(cutoffs, 0)
    reciprocal_sum = 0.0
    single = multi = out_of_scope = no_result = 0
    in_scope_top1: list[float] = []
    out_of_scope_top1: list[float] = []
    misses: list[Miss] = []

    for item in questions:
        passages = list(search(item.question, top_k))[:top_k]
        if not passages:
            no_result += 1
        top1 = float(passages[0]["score"]) if passages else None

        if not item.in_scope:
            out_of_scope += 1
            if top1 is not None:
                out_of_scope_top1.append(top1)
            continue

        if len(item.expect) == 1:
            single += 1
        else:
            multi += 1
        if top1 is not None:
            in_scope_top1.append(top1)

        doc_rank = _worst_rank(passages, item, with_section=False)
        section_rank = _worst_rank(passages, item, with_section=True)
        for k in cutoffs:
            doc_hits[k] += doc_rank is not None and doc_rank <= k
            section_hits[k] += section_rank is not None and section_rank <= k
        if doc_rank is not None:
            reciprocal_sum += 1 / doc_rank

        found_at_first = len(item.expect) == 1 and doc_rank == 1
        if not found_at_first and not (len(item.expect) > 1 and doc_rank is not None):
            misses.append(Miss(
                question=item.question,
                expected=item.expect,
                top=tuple((str(p["slug"]), str(p.get("section", "")), float(p["score"])) for p in passages[:MISS_TOP_SHOWN]),
            ))

    in_scope = single + multi
    return EvalReport(
        top_k=top_k,
        cutoffs=cutoffs,
        single_count=single,
        multi_count=multi,
        out_of_scope_count=out_of_scope,
        recall_doc={k: _ratio(doc_hits[k], in_scope) for k in cutoffs},
        recall_section={k: _ratio(section_hits[k], in_scope) for k in cutoffs},
        mrr=_ratio(reciprocal_sum, in_scope),
        in_scope_top1=tuple(in_scope_top1),
        out_of_scope_top1=tuple(out_of_scope_top1),
        misses=tuple(misses),
        no_result_count=no_result,
    )


# --------------------------------------------------------------------------------------------- in kết quả

def _short_section(section: str) -> str:
    """Bỏ tiêu đề tài liệu ở đầu đường dẫn mục (`<tiêu đề> › <mục>` -> `<mục>`)."""
    return section.split(SECTION_SEPARATOR, 1)[1] if SECTION_SEPARATOR in section else section


def _fmt(value: float | None) -> str:
    return "không có số liệu" if value is None else f"{value:.4f}"


def format_report(report: EvalReport) -> str:
    lines = [
        f"Đánh giá truy xuất: {report.total_count} câu hỏi, top-k = {report.top_k}",
        f"  trong phạm vi: {report.in_scope_count} (một nguồn {report.single_count}, hai nguồn {report.multi_count});"
        f" ngoài phạm vi: {report.out_of_scope_count}",
        "",
        "Mức tài liệu (đoạn thuộc đúng slug):",
    ]
    lines += [f"  recall@{k}: {report.recall_doc[k]:.3f}" for k in report.cutoffs]
    lines.append(f"  MRR: {report.mrr:.3f}")
    lines += ["", "Mức mục (đúng slug và đúng mục ##):"]
    lines += [f"  recall@{k}: {report.recall_section[k]:.3f}" for k in report.cutoffs]

    lines += [
        "",
        "Điểm của đoạn hạng 1:",
        f"  câu trong phạm vi: thấp nhất {_fmt(report.in_scope_min)}, trung vị {_fmt(report.in_scope_median)}",
        f"  câu ngoài phạm vi: cao nhất {_fmt(report.out_of_scope_max)}, trung vị {_fmt(report.out_of_scope_median)}",
    ]
    if report.groups_overlap is None:
        lines.append("  Không đủ số liệu của cả hai nhóm để gợi ý POLICY_MIN_SCORE.")
    elif report.groups_overlap:
        lines.append(
            "  Hai nhóm điểm chồng lấn (điểm cao nhất ngoài phạm vi không thấp hơn điểm thấp nhất trong phạm vi):"
            " không gợi ý POLICY_MIN_SCORE, một ngưỡng sẽ cắt nhầm câu đúng hoặc để lọt câu ngoài phạm vi."
        )
    else:
        lines.append(
            f"  Gợi ý POLICY_MIN_SCORE = {report.suggested_min_score:.4f}"
            " (trung điểm giữa điểm cao nhất ngoài phạm vi và điểm thấp nhất trong phạm vi)."
        )

    if report.no_result_count:
        lines += ["", f"Lưu ý: {report.no_result_count} câu không nhận được đoạn nào."]
    lines += ["", f"Câu trượt (không trúng ở hạng 1; câu hai nguồn: thiếu tài liệu trong top-{report.top_k}): {len(report.misses)}"]
    for miss in report.misses:
        lines.append(f"- {miss.question}")
        lines.append("    Kỳ vọng: " + "; ".join(f"{e.slug} › {e.section}" for e in miss.expected))
        if miss.top:
            lines.append("    Thực tế: " + " | ".join(f"{slug} › {_short_section(section)} · {score:.4f}" for slug, section, score in miss.top))
        else:
            lines.append("    Thực tế: không có đoạn nào")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------- nối dây thật

def _build_search() -> SearchFn:
    """Dựng `search` thật: embedder Gemini + kho Milvus chỉ đọc, ngưỡng điểm 0 (không lọc)."""
    # Import muộn: google-genai và pymilvus không được kéo vào khi chỉ import module này (kiểm thử, `--help`).
    from app.domains.policy.application.services.retrieval import PolicySearchService
    from app.domains.policy.infrastructure.embedding.gemini import build_embedder
    from app.domains.policy.infrastructure.vectorstore.milvus_store import build_milvus_store

    service = PolicySearchService(
        lambda: build_milvus_store(settings.milvus_uri, settings.milvus_token, settings.milvus_collection, read_only=True),
        lambda: build_embedder(settings.gemini_api_key, settings.gemini_embedding_model, settings.gemini_base_url),
        min_score=0.0,
    )

    def search(query: str, top_k: int) -> list[dict[str, Any]]:
        result = service.search(query, top_k=top_k)
        if "error" in result:  # thông báo của dịch vụ là chuỗi tiếng Việt cố định, không chứa khoá hay địa chỉ
            raise SearchFailed(result["error"])
        return result["passages"]

    return search


def _top_k_arg(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("phải là số nguyên") from None
    if not 1 <= number <= MAX_TOP_K:
        raise argparse.ArgumentTypeError(f"phải nằm trong khoảng 1 đến {MAX_TOP_K}")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.eval_retrieval", description="Đo chất lượng truy xuất chính sách.")
    parser.add_argument("--top-k", type=_top_k_arg, default=5, help=f"số đoạn lấy cho mỗi câu (1-{MAX_TOP_K}, mặc định 5)")
    parser.add_argument("--eval", type=Path, default=DEFAULT_EVAL_PATH, help="file câu hỏi (mặc định data/policy_eval.yaml)")
    args = parser.parse_args(argv)

    try:
        items = load_eval_set(args.eval)
    except EvalSetError as exc:
        print(f"Lỗi: file câu hỏi không hợp lệ: {exc}", file=sys.stderr)
        return 2
    if not settings.gemini_api_key:
        print("Lỗi: chưa đặt GEMINI_API_KEY nên không nhúng được câu hỏi.", file=sys.stderr)
        return 2

    try:
        report = evaluate(_build_search(), items, args.top_k)
    except SearchFailed as exc:
        print(f"Lỗi: không truy xuất được: {exc}", file=sys.stderr)
        return 2
    if report.no_result_count == report.total_count:
        print(
            "Lỗi: kho chính sách không trả đoạn nào cho bất kỳ câu nào; hãy chạy "
            "`python -m app.cli ingest-policies data/policies` (cùng GEMINI_API_KEY và MILVUS_URI) rồi thử lại.",
            file=sys.stderr,
        )
        return 2
    print(format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
