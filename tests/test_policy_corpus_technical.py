"""Corpus kỹ thuật thi công trong data/policies/: đúng 8 tài liệu, khớp danh mục dữ liệu giả."""
import re
from pathlib import Path

import pytest

from app.domains.policy.application.services.corpus import PolicyDocument, load_policy_dir
from scripts.fake_catalog import COMPANY_NAME, PREP_STEPS, PROCESS_POOLS, WORK_ITEM_CATALOG

POLICY_DIR = Path(__file__).resolve().parent.parent / "data" / "policies"
DEMO_NOTE = "Tài liệu giả lập cho bản demo; công ty, sản phẩm đều là bịa."
ALL_ITEMS = [item.name for item in WORK_ITEM_CATALOG]

# slug -> (các mục `##` theo đúng thứ tự, chuỗi số liệu cố định phải có trong thân)
EXPECTED = {
    "xu-ly-be-mat": (
        ["Vệ sinh bề mặt", "Xử lý khuyết tật", "Chà nhám", "Kiểm tra độ ẩm"],
        ["16%", "28 ngày", "0,3 mm"],
    ),
    "thi-cong-son-nuoc-va-ba-matit": (
        ["Sơn lót chống kiềm", "Bả matit 2 lớp", "Sơn phủ 2 lớp", "Thời gian khô"],
        ["4 giờ", "6 giờ", "2 giờ"],
    ),
    "thi-cong-chong-tham": (
        ["Chuẩn bị nền", "Chống thấm lớp 1", "Chống thấm lớp 2", "Thử ngâm nước", "Vì sao hệ đàn hồi (PU) đắt hơn"],
        ["vuông góc", "6 giờ", "20 cm", "48 giờ"],
    ),
    "thi-cong-kim-loai-va-chong-nong": (
        ["Chà nhám và khử gỉ", "Sơn lót chống gỉ", "Sơn phủ", "Sơn chống nóng mái tôn"],
        ["24 giờ", "45 °C"],
    ),
    "thi-cong-epoxy-va-hieu-ung-da": (
        ["Điều kiện nền epoxy", "Trộn hai thành phần", "Hiệu ứng đá", "Vì sao nhân công cao"],
        ["28 ngày", "40 phút", "1,5 lần"],
    ),
    "dinh-muc-hao-hut-va-so-lop": (
        ["Hao hụt thi công", "Số lớp theo hạng mục", "Quy đổi ra thùng"],
        ["3%", "6%", "8%", "12%", "làm tròn lên"],
    ),
    "dinh-muc-nhan-cong-va-to-doi": (
        ["Ngày công trên m²", "Hệ số theo hạng mục", "Hệ số nhân công", "Đội nhà và thuê ngoài"],
        ["0,015", "0,04", "1,2", "1,4", "1,3", "1,5", "1,05", "1,25", "has_kn", "all_out"],
    ),
    "dieu-kien-thi-cong-va-an-toan": (
        ["Thời tiết", "Giàn giáo và làm việc trên cao", "Bảo vệ đồ đạc và khu vực xung quanh", "Chất thải sơn"],
        ["85%", "2 m", "dây an toàn", "đầu mỗi ca"],
    ),
}
# Hai thông số bắt buộc trong tài liệu nhân công / hao hụt (theo kế hoạch).
APPLIES_TO_ALL = {
    "dinh-muc-hao-hut-va-so-lop",
    "dinh-muc-nhan-cong-va-to-doi",
    "dieu-kien-thi-cong-va-an-toan",
}


@pytest.fixture(scope="module")
def technical() -> dict[str, PolicyDocument]:
    docs = [d for d in load_policy_dir(POLICY_DIR) if d.front.doc_type == "technical"]
    return {d.front.slug: d for d in docs}


def headings(doc: PolicyDocument) -> list[str]:
    return [line[3:].strip() for line in doc.body.split("\n") if line.startswith("## ")]


def test_exactly_the_eight_technical_documents(technical):
    assert set(technical) == set(EXPECTED)
    for slug, doc in technical.items():
        assert doc.source_name == f"{slug}.md"


@pytest.mark.parametrize("slug", sorted(EXPECTED))
def test_sections_match_the_plan(technical, slug):
    assert headings(technical[slug]) == EXPECTED[slug][0]


@pytest.mark.parametrize("slug", sorted(EXPECTED))
def test_pinned_figures_present(technical, slug):
    body = technical[slug].body
    missing = [needle for needle in EXPECTED[slug][1] if needle not in body]
    assert not missing, f"{slug} thiếu: {missing}"


def test_labor_and_waste_pinned_values(technical):
    labor = technical["dinh-muc-nhan-cong-va-to-doi"].body
    for needle in ("0,015", "0,04", "1,05", "1,25"):
        assert needle in labor
    waste = technical["dinh-muc-hao-hut-va-so-lop"].body
    assert "3%" in waste and "12%" in waste


@pytest.mark.parametrize("slug", sorted(EXPECTED))
def test_word_count_in_range(technical, slug):
    words = len(technical[slug].body.split())
    assert 500 <= words <= 1000, f"{slug}: {words} từ"


@pytest.mark.parametrize("slug", sorted(EXPECTED))
def test_opening_demo_note_and_company(technical, slug):
    body = technical[slug].body
    before_first_section = body.split("\n## ", 1)[0]
    assert DEMO_NOTE in before_first_section
    assert COMPANY_NAME in body


def test_every_work_item_covered_by_some_document(technical):
    covered = {name for doc in technical.values() for name in doc.front.applies_to}
    assert set(ALL_ITEMS) <= covered


def test_applies_to_values(technical):
    assert technical["xu-ly-be-mat"].front.applies_to == sorted(PREP_STEPS)
    for slug in APPLIES_TO_ALL:
        assert technical[slug].front.applies_to == ALL_ITEMS
    chong_tham = technical["thi-cong-chong-tham"].front.applies_to
    assert chong_tham == ["Chống thấm sân thượng", "Chống thấm nhà vệ sinh", "Chống thấm tường ngoài"]
    for slug, doc in technical.items():
        for name in doc.front.applies_to:
            assert name in ALL_ITEMS or name in PREP_STEPS, f"{slug}: {name} không có trong danh mục"


def test_every_process_step_mentioned(technical):
    text = "\n".join(doc.body for doc in technical.values()).lower()
    steps = {step for pool in PROCESS_POOLS.values() for step in pool}
    missing = sorted(step for step in steps if step.lower() not in text)
    assert not missing, f"bước chưa được nhắc: {missing}"


def _catalog_words() -> set[str]:
    words = set(re.findall(r"[A-Za-z]+", COMPANY_NAME))
    for item in WORK_ITEM_CATALOG:
        for _, line, product in item.products:
            words.update(re.findall(r"[A-Za-z]+", f"{line} {product}"))
    return words


def _mid_sentence_latin_capitals(body: str) -> set[str]:
    found = set()
    for line in body.split("\n"):
        line = re.sub(r"^\s*(#+|[-*]|\d+\.)\s*", "", line).replace("**", "")
        for sentence in re.split(r"[.!?:;]\s+", line):
            tokens = sentence.split()[1:]  # bỏ từ đầu câu
            for token in tokens:
                for word in re.findall(r"\b[A-Z][a-zA-Z]+\b", token):
                    if not word.isupper():
                        found.add(word)
    return found


@pytest.mark.parametrize("slug", sorted(EXPECTED))
def test_no_brand_outside_catalog_and_no_standards(technical, slug):
    body = technical[slug].body
    unknown = _mid_sentence_latin_capitals(body) - _catalog_words()
    assert not unknown, f"{slug}: tên lạ (thương hiệu ngoài danh mục?): {sorted(unknown)}"
    assert not re.search(r"\b(TCVN|ISO|ASTM|DIN)\b", body), "không viện dẫn tiêu chuẩn thật"
