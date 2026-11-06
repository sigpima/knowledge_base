"""Bộ cắt chunk Markdown theo heading cho tài liệu chính sách."""
import statistics
from pathlib import Path

from app.domains.policy.application.services.chunker import PolicyChunk, chunk_document
from app.domains.policy.application.services.corpus import (
    PolicyDocument,
    PolicyFrontMatter,
    load_policy_dir,
)

POLICY_DIR = Path(__file__).resolve().parent.parent / "data" / "policies"
TITLE = "Quy định thử"


def make_doc(body: str, title: str = TITLE) -> PolicyDocument:
    front = PolicyFrontMatter(slug="quy-dinh-thu", title=title, doc_type="technical")
    return PolicyDocument(front=front, body=body.strip(), source_name="quy-dinh-thu.md", content_hash="x")


def test_two_h2_sections_get_own_paths():
    chunks = chunk_document(make_doc("## Một\n\nNội dung một.\n\n## Hai\n\nNội dung hai."))

    assert [(c.section_path, c.text) for c in chunks] == [
        (f"{TITLE} › Một", "Nội dung một."),
        (f"{TITLE} › Hai", "Nội dung hai."),
    ]


def test_h3_nested_in_h2_gives_three_level_path():
    body = "## Mục lớn\n\nMở đầu.\n\n### Mục con\n\nChi tiết con.\n\n### Mục con khác\n\nChi tiết khác."
    chunks = chunk_document(make_doc(body))

    assert [c.section_path for c in chunks] == [
        f"{TITLE} › Mục lớn",
        f"{TITLE} › Mục lớn › Mục con",
        f"{TITLE} › Mục lớn › Mục con khác",
    ]


def test_h3_stack_resets_on_next_h2():
    body = "## A\n\n### A1\n\nx\n\n## B\n\ny"
    assert [c.section_path for c in chunk_document(make_doc(body))] == [
        f"{TITLE} › A › A1",
        f"{TITLE} › B",
    ]


def test_heading_without_body_is_dropped():
    body = "## Trống\n\n## Có thân\n\nNội dung.\n\n## Cha trống\n\n### Con\n\nNội dung con."
    assert [c.section_path for c in chunk_document(make_doc(body))] == [
        f"{TITLE} › Có thân",
        f"{TITLE} › Cha trống › Con",
    ]


def test_text_before_first_heading_belongs_to_title_path():
    body = "# Quy định thử\n\nTài liệu giả lập.\n\n## Mục\n\nNội dung."
    chunks = chunk_document(make_doc(body))

    assert [(c.section_path, c.text) for c in chunks] == [
        (TITLE, "Tài liệu giả lập."),
        (f"{TITLE} › Mục", "Nội dung."),
    ]


def test_deeper_headings_stay_as_plain_text_of_enclosing_section():
    body = "## Mục\n\n### Con\n\nA.\n\n#### Sâu\n\nB."
    chunks = chunk_document(make_doc(body))

    assert len(chunks) == 1
    assert chunks[0].section_path == f"{TITLE} › Mục › Con"
    assert chunks[0].text == "A.\n\n#### Sâu\n\nB."


def test_paragraphs_are_packed_up_to_max_chars_then_split():
    paragraphs = [f"Đoạn số {i} " + "x" * 30 + "." for i in range(6)]  # mỗi đoạn ~ 42 ký tự
    chunks = chunk_document(make_doc("## Mục\n\n" + "\n\n".join(paragraphs)), max_chars=100)

    assert len(chunks) == 3
    assert all(len(c.text) <= 100 for c in chunks)
    assert chunks[0].text == "\n\n".join(paragraphs[:2])
    assert "\n\n".join(c.text for c in chunks) == "\n\n".join(paragraphs)


def test_everything_fits_in_one_chunk_when_small():
    body = "## Mục\n\nMột.\n\nHai.\n\nBa."
    chunks = chunk_document(make_doc(body))

    assert [c.text for c in chunks] == ["Một.\n\nHai.\n\nBa."]


def test_long_paragraph_splits_on_sentence_boundary_not_mid_word():
    sentences = ["Câu thứ nhất rất là dài dòng.", "Câu thứ hai cũng không ngắn đâu?", "Câu thứ ba kết thúc ở đây!"]
    chunks = chunk_document(make_doc("## Mục\n\n" + " ".join(sentences)), max_chars=40)

    assert [c.text for c in chunks] == sentences
    assert all(len(c.text) <= 40 for c in chunks)
    assert all(c.text.endswith((".", "?", "!")) for c in chunks)
    assert " ".join(c.text for c in chunks) == " ".join(sentences)


def test_single_sentence_longer_than_max_falls_back_to_word_boundary():
    words = [f"từ{i}" for i in range(40)]
    sentence = " ".join(words) + "."
    chunks = chunk_document(make_doc("## Mục\n\n" + sentence), max_chars=50)

    assert len(chunks) > 1
    assert all(len(c.text) <= 50 for c in chunks)
    rejoined = " ".join(c.text for c in chunks)
    assert rejoined == sentence
    for chunk in chunks:
        assert set(chunk.text.rstrip(".").split(" ")) <= set(words)


def test_list_block_without_blank_lines_stays_whole():
    items = "\n".join(f"{i}. Mục thứ {i} của danh sách." for i in range(1, 6))
    other = "Đoạn khác " + "y" * 60 + "."
    chunks = chunk_document(make_doc(f"## Mục\n\n{items}\n\n{other}"), max_chars=len(items) + 10)

    assert chunks[0].text == items
    assert chunks[1].text == other


def test_table_block_is_one_paragraph():
    table = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
    chunks = chunk_document(make_doc(f"## Mục\n\n{table}"))

    assert [c.text for c in chunks] == [table]


def test_hash_lines_inside_code_fence_are_not_headings():
    body = "## Mục\n\nTrước.\n\n```\n# không phải heading\n## cũng không\n```\n\nSau."
    chunks = chunk_document(make_doc(body))

    assert [c.section_path for c in chunks] == [f"{TITLE} › Mục"]
    assert "# không phải heading" in chunks[0].text
    assert "## cũng không" in chunks[0].text


def test_blank_line_inside_code_fence_does_not_split_block():
    body = "## Mục\n\n```\na\n\nb\n```"
    chunks = chunk_document(make_doc(body))

    assert [c.text for c in chunks] == ["```\na\n\nb\n```"]


def test_index_is_continuous_from_zero_across_sections():
    body = "## A\n\n" + "\n\n".join(f"Đoạn {i}." for i in range(5)) + "\n\n## B\n\nKết."
    chunks = chunk_document(make_doc(body), max_chars=20)

    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert len(chunks) > 2


def test_chunking_is_deterministic():
    body = "## A\n\n" + " ".join(f"Câu {i}." for i in range(80)) + "\n\n## B\n\nKết."
    assert chunk_document(make_doc(body), max_chars=120) == chunk_document(make_doc(body), max_chars=120)


def test_embed_text_prefixes_section_path():
    chunk = PolicyChunk(index=0, section_path="T › A", text="Nội dung.")

    assert chunk.embed_text == "T › A\n\nNội dung."


def test_empty_body_gives_no_chunks():
    assert chunk_document(make_doc("")) == []


def test_real_corpus_chunk_sizes_and_count_are_sane():
    documents = load_policy_dir(POLICY_DIR)
    all_chunks = [chunk for doc in documents for chunk in chunk_document(doc)]
    lengths = [len(chunk.text) for chunk in all_chunks]

    assert all(length <= 1000 for length in lengths), max(lengths)
    assert 30 <= len(all_chunks) <= 400, len(all_chunks)
    assert statistics.median(lengths) > 100


def test_real_corpus_paths_point_at_h2_sections():
    for doc in load_policy_dir(POLICY_DIR):
        h2_titles = {line[3:].strip() for line in doc.body.split("\n") if line.startswith("## ")}
        chunks = chunk_document(doc)
        assert chunks, doc.source_name
        assert {c.section_path for c in chunks} <= {doc.front.title} | {
            f"{doc.front.title} › {h}" for h in h2_titles
        }
        assert {f"{doc.front.title} › {h}" for h in h2_titles} <= {c.section_path for c in chunks}
