"""Corpus bảo hành & nghiệm thu trong data/policies/: đúng 4 tài liệu, khớp danh mục dữ liệu giả."""
import re

import pytest

from app.domains.policy.application.services.corpus import PolicyDocument, load_policy_dir
from scripts.fake_catalog import COMPANY_NAME, PAYMENT_TRIGGERS
from tests.test_policy_corpus_technical import (
    ALL_ITEMS,
    DEMO_NOTE,
    POLICY_DIR,
    _catalog_words,
    _mid_sentence_latin_capitals,
    has_figure,
    headings,
)

# slug -> (các mục `##` theo đúng thứ tự, chuỗi số liệu/cụm từ cố định phải có trong thân)
EXPECTED = {
    "chinh-sach-bao-hanh": (
        [
            "Nguyên tắc: báo giá ghi riêng thì ưu tiên",
            "Thời hạn tiêu chuẩn theo nhóm hạng mục",
            "Gia hạn bảo hành",
            "Giữ lại bảo hành",
            "Bảo hành bắt đầu từ khi nào",
        ],
        ["12 tháng", "18 tháng", "24 tháng", "36 tháng", "5%", "extend_percent", "extend_period"],
    ),
    "loai-tru-bao-hanh": (
        ["Lỗi được bảo hành", "Lỗi không được bảo hành", "Hao mòn tự nhiên"],
        ["bong tróc", "phồng rộp", "nứt chân chim", "0,3 mm", "tháng thứ 12"],
    ),
    "quy-trinh-nghiem-thu": (
        [
            "Nghiệm thu giai đoạn 1",
            "Nghiệm thu giai đoạn 2",
            "Nghiệm thu bàn giao hoàn công",
            "Biên bản và hồ sơ",
            "Liên hệ với đợt thanh toán",
        ],
        ["3 ngày làm việc", "48 giờ", "ngâm nước"],
    ),
    "quy-trinh-xu-ly-khieu-nai-bao-hanh": (
        ["Tiếp nhận", "Khảo sát hiện trường", "Khắc phục", "Từ chối bảo hành"],
        ["48 giờ", "5 ngày làm việc", "15 ngày làm việc", "văn bản"],
    ),
}


@pytest.fixture(scope="module")
def warranty() -> dict[str, PolicyDocument]:
    docs = [d for d in load_policy_dir(POLICY_DIR) if d.front.doc_type == "warranty"]
    return {d.front.slug: d for d in docs}


def test_exactly_the_four_warranty_documents(warranty):
    assert set(warranty) == set(EXPECTED)
    for slug, doc in warranty.items():
        assert doc.source_name == f"{slug}.md"


@pytest.mark.parametrize("slug", sorted(EXPECTED))
def test_sections_match_the_plan(warranty, slug):
    assert headings(warranty[slug]) == EXPECTED[slug][0]


@pytest.mark.parametrize("slug", sorted(EXPECTED))
def test_pinned_figures_present(warranty, slug):
    body = warranty[slug].body
    missing = [needle for needle in EXPECTED[slug][1] if not has_figure(body, needle)]
    assert not missing, f"{slug} thiếu: {missing}"


def test_warranty_policy_covers_extension_semantics(warranty):
    body = warranty["chinh-sach-bao-hanh"].body
    assert "gia hạn" in body and "trả thêm" in body
    assert "quy ước" in body and "demo" in body, "phải nêu rõ đây là quy ước của bản demo"


def test_acceptance_names_every_payment_trigger_verbatim(warranty):
    body = warranty["quy-trinh-nghiem-thu"].body
    missing = [desc for _, desc in PAYMENT_TRIGGERS if desc not in body]
    assert not missing, f"thiếu mốc thanh toán: {missing}"


def test_waterproofing_acceptance_matches_technical_rule(warranty):
    """Cùng một quy tắc với thi-cong-chong-tham: nghiệm thu chống thấm chỉ sau 48 giờ ngâm nước đạt."""
    body = warranty["quy-trinh-nghiem-thu"].body
    assert re.search(r"chống thấm[^.]*ngâm nước 48 giờ", body, re.IGNORECASE)


@pytest.mark.parametrize("slug", sorted(EXPECTED))
def test_word_count_in_range(warranty, slug):
    words = len(warranty[slug].body.split())
    assert 500 <= words <= 1000, f"{slug}: {words} từ"


@pytest.mark.parametrize("slug", sorted(EXPECTED))
def test_every_section_has_content_and_a_reason(warranty, slug):
    sections = re.split(r"(?m)^## .*$", warranty[slug].body)[1:]
    assert len(sections) == len(EXPECTED[slug][0])
    for title, text in zip(EXPECTED[slug][0], sections):
        assert len(text.split()) >= 40, f"{slug}: mục '{title}' quá ngắn"
        assert "Lý do" in text, f"{slug}: mục '{title}' thiếu lý do"


@pytest.mark.parametrize("slug", sorted(EXPECTED))
def test_opening_demo_note_and_company(warranty, slug):
    body = warranty[slug].body
    before_first_section = body.split("\n## ", 1)[0]
    assert DEMO_NOTE in before_first_section
    assert COMPANY_NAME in body


def test_applies_to_every_work_item(warranty):
    for slug, doc in warranty.items():
        assert doc.front.applies_to == ALL_ITEMS, slug


@pytest.mark.parametrize("slug", sorted(EXPECTED))
def test_no_brand_outside_catalog_and_no_standards(warranty, slug):
    body = warranty[slug].body
    unknown = _mid_sentence_latin_capitals(body) - _catalog_words()
    assert not unknown, f"{slug}: tên lạ (thương hiệu ngoài danh mục?): {sorted(unknown)}"
    assert not re.search(r"\b(TCVN|ISO|ASTM|DIN)\b", body), "không viện dẫn tiêu chuẩn thật"
