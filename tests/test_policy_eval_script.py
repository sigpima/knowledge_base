"""Kịch bản đánh giá truy xuất: số đo tính đúng trên đầu vào dựng tay, chạy được trên corpus thật, thoát mã 2 khi thiếu khoá."""
from pathlib import Path

import pytest

from app.domains.policy.application.services.corpus import load_policy_dir
from app.domains.policy.application.services.ingest import ingest_policy
from app.domains.policy.application.services.retrieval import PolicySearchService
from app.infrastructure.config.config import settings
from scripts import eval_retrieval
from scripts.eval_retrieval import (
    EvalItem,
    EvalSetError,
    Expectation,
    SearchFailed,
    evaluate,
    format_report,
    load_eval_set,
)
from tests.policy_fakes import HashingEmbedder

ROOT = Path(__file__).parent.parent
SECRETS = ("tok-s3cret-value", "AIza-fake-key", "http://secret-host.invalid:19530")


def p(slug, section, score):
    """Một đoạn dạng kết quả tool: `section` là đường dẫn `<tiêu đề> › <mục>`."""
    return {"slug": slug, "title": f"Tài liệu {slug}", "doc_type": "technical", "section": f"Tài liệu {slug} › {section}",
            "text": "nội dung", "score": score}


def single(question, slug, section):
    return EvalItem(question, (Expectation(slug, section),))


def stub_search(table):
    calls = []

    def search(query, top_k):
        calls.append((query, top_k))
        return list(table[query])

    search.calls = calls
    return search


# ---------------------------------------------------------------------------------------------- evaluate()

@pytest.fixture
def hand_made():
    items = [
        single("q1", "a", "S1"),
        single("q2", "b", "S2"),
        single("q3", "c", "S3"),
        EvalItem("q4", (Expectation("a", "S1"), Expectation("b", "S2"))),
        EvalItem("o1", ()),
        EvalItem("o2", ()),
    ]
    table = {
        "q1": [p("a", "S1", 0.9), p("b", "X", 0.8), p("c", "X", 0.7), p("d", "X", 0.6), p("e", "X", 0.5)],
        "q2": [p("a", "X", 0.8), p("b", "Khác", 0.7), p("c", "X", 0.6), p("b", "S2", 0.5), p("e", "X", 0.4)],
        "q3": [p("a", "X", 0.6), p("b", "X", 0.5), p("d", "X", 0.4)],
        "q4": [p("a", "S1", 0.9), p("c", "X", 0.8), p("b", "S2", 0.7), p("d", "X", 0.6), p("e", "X", 0.5)],
        "o1": [p("a", "X", 0.4), p("b", "X", 0.3)],
        "o2": [p("c", "X", 0.55)],
    }
    return items, stub_search(table)


def test_search_is_called_once_per_question_with_the_top_k(hand_made):
    items, search = hand_made

    evaluate(search, items, top_k=5)

    assert search.calls == [(item.question, 5) for item in items]


def test_counts_per_category(hand_made):
    items, search = hand_made

    report = evaluate(search, items, top_k=5)

    assert (report.single_count, report.multi_count, report.out_of_scope_count) == (3, 1, 2)
    assert report.in_scope_count == 4
    assert report.cutoffs == (1, 3, 5)


def test_document_level_recall_is_computed_exactly(hand_made):
    items, search = hand_made

    report = evaluate(search, items, top_k=5)

    # q1 trúng ở hạng 1; q2 ở hạng 2; q3 trượt; q4 cần cả a (hạng 1) và b (hạng 3).
    assert report.recall_doc == {1: pytest.approx(0.25), 3: pytest.approx(0.75), 5: pytest.approx(0.75)}


def test_section_level_recall_requires_the_section_to_match(hand_made):
    items, search = hand_made

    report = evaluate(search, items, top_k=5)

    # q1: mục đúng ở hạng 1. q2: b nằm ở hạng 2 nhưng sai mục; mục đúng tới hạng 4. q4: a/S1 hạng 1 và b/S2 hạng 3.
    assert report.recall_section == {1: pytest.approx(0.25), 3: pytest.approx(0.5), 5: pytest.approx(0.75)}


def test_mrr_uses_first_expected_slug_and_the_last_one_for_multi_source(hand_made):
    items, search = hand_made

    report = evaluate(search, items, top_k=5)

    assert report.mrr == pytest.approx((1 + 1 / 2 + 0 + 1 / 3) / 4)


def test_score_statistics_and_separated_groups_give_the_midpoint(hand_made):
    items, search = hand_made

    report = evaluate(search, items, top_k=5)

    assert report.in_scope_top1 == (0.9, 0.8, 0.6, 0.9)
    assert report.out_of_scope_top1 == (0.4, 0.55)
    assert report.in_scope_min == 0.6
    assert report.in_scope_median == pytest.approx(0.85)
    assert report.out_of_scope_max == 0.55
    assert report.out_of_scope_median == pytest.approx(0.475)
    assert report.groups_overlap is False
    assert report.suggested_min_score == pytest.approx(0.575)


def test_overlapping_groups_give_no_suggestion():
    items = [single("q", "a", "S"), EvalItem("o", ())]
    search = stub_search({"q": [p("a", "S", 0.6)], "o": [p("b", "X", 0.7)]})

    report = evaluate(search, items, top_k=5)

    assert report.groups_overlap is True
    assert report.suggested_min_score is None


def test_touching_groups_count_as_overlapping():
    items = [single("q", "a", "S"), EvalItem("o", ())]
    search = stub_search({"q": [p("a", "S", 0.6)], "o": [p("b", "X", 0.6)]})

    report = evaluate(search, items, top_k=5)

    assert report.groups_overlap is True and report.suggested_min_score is None


def test_missed_questions_list_expected_and_top_three_actual(hand_made):
    items, search = hand_made

    report = evaluate(search, items, top_k=5)

    # q4 (đa nguồn) trúng ở top-5 nên không phải câu trượt; q2 (hạng 2) và q3 (không có) thì có.
    assert [miss.question for miss in report.misses] == ["q2", "q3"]
    q2 = report.misses[0]
    assert q2.expected == (Expectation("b", "S2"),)
    assert [(slug, score) for slug, _, score in q2.top] == [("a", 0.8), ("b", 0.7), ("c", 0.6)]
    assert q2.top[1][1] == "Tài liệu b › Khác"


def test_passages_beyond_top_k_are_ignored(hand_made):
    items, search = hand_made

    report = evaluate(search, items, top_k=3)

    assert report.cutoffs == (1, 3)
    assert report.recall_doc == {1: pytest.approx(0.25), 3: pytest.approx(0.75)}
    assert report.recall_section == {1: pytest.approx(0.25), 3: pytest.approx(0.5)}


def test_a_question_without_any_passage_counts_as_a_miss_and_has_no_score():
    items = [single("q", "a", "S"), EvalItem("o", ())]
    search = stub_search({"q": [], "o": []})

    report = evaluate(search, items, top_k=5)

    assert report.no_result_count == 2
    assert report.mrr == 0.0 and report.recall_doc[1] == 0.0
    assert report.in_scope_top1 == () and report.out_of_scope_top1 == ()
    assert report.in_scope_min is None and report.out_of_scope_max is None
    assert report.suggested_min_score is None and report.groups_overlap is None


def test_section_match_is_on_the_last_path_segment_not_a_substring():
    items = [single("q", "a", "Chà nhám")]
    search = stub_search({"q": [p("a", "Chà nhám và khử gỉ", 0.9)]})

    report = evaluate(search, items, top_k=5)

    assert report.recall_doc[1] == 1.0 and report.recall_section[1] == 0.0


def test_only_out_of_scope_questions_is_fine():
    report = evaluate(stub_search({"o": [p("a", "X", 0.3)]}), [EvalItem("o", ())], top_k=5)

    assert report.in_scope_count == 0
    assert report.mrr == 0.0 and report.recall_doc == {1: 0.0, 3: 0.0, 5: 0.0}
    assert report.suggested_min_score is None


# ------------------------------------------------------------------------------------------ format_report()

def test_report_text_is_vietnamese_and_lists_metrics_misses_and_suggestion(hand_made):
    items, search = hand_made

    text = format_report(evaluate(search, items, top_k=5))

    for needle in ("recall@1", "recall@3", "recall@5", "MRR", "Câu trượt", "q2", "q3", "POLICY_MIN_SCORE", "0.5750"):
        assert needle in text
    assert "b › Khác · 0.7000" in text  # định dạng `slug › mục · điểm`, bỏ tiêu đề tài liệu khỏi đường dẫn mục
    assert "Kỳ vọng" in text


def test_report_text_states_overlap_without_inventing_a_number():
    items = [single("q", "a", "S"), EvalItem("o", ())]
    search = stub_search({"q": [p("a", "S", 0.6)], "o": [p("b", "X", 0.7)]})

    text = format_report(evaluate(search, items, top_k=5))

    assert "chồng lấn" in text
    assert "Gợi ý POLICY_MIN_SCORE" not in text


# ------------------------------------------------------------------------------------------ load_eval_set()

def write(tmp_path, content):
    path = tmp_path / "eval.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_loader_reads_single_multi_and_null_shapes(tmp_path):
    path = write(tmp_path, """
# chú thích bị bỏ qua
- question: "Một?"
  expect: {slug: a, section: S}
- question: "Hai?"
  expect:
    - {slug: a, section: S}
    - {slug: b, section: T}
- question: "Ba?"
  expect: null
""")

    one, two, three = load_eval_set(path)

    assert one.expect == (Expectation("a", "S"),)
    assert two.expect == (Expectation("a", "S"), Expectation("b", "T"))
    assert three.expect == ()


@pytest.mark.parametrize(
    "content",
    [
        "không phải YAML: [",
        "{question: x}",
        "[]",
        "- question: ''\n  expect: null",
        "- question: x",
        "- question: x\n  expect: {slug: a}",
        "- question: x\n  expect: {slug: a, section: S, thua: 1}",
        "- question: x\n  expect: [{slug: a, section: S}]",
        "- question: x\n  expect: [{slug: a, section: S}, {slug: a, section: T}]",
        "- question: x\n  expect: null\n  them: 1",
        "- {question: x, expect: null}\n- {question: x, expect: null}",
    ],
)
def test_loader_rejects_malformed_files_with_eval_set_error(tmp_path, content):
    with pytest.raises(EvalSetError):
        load_eval_set(write(tmp_path, content))


def test_loader_reports_a_missing_file_as_eval_set_error(tmp_path):
    with pytest.raises(EvalSetError):
        load_eval_set(tmp_path / "khong-co.yaml")


# --------------------------------------------------------------------------------- end to end, real corpus

def test_evaluate_runs_on_the_real_corpus_and_eval_set_with_the_hashing_embedder(policy_store):
    embedder = HashingEmbedder()
    for doc in load_policy_dir(ROOT / "data" / "policies"):
        ingest_policy(policy_store, embedder, doc)
    service = PolicySearchService(lambda: policy_store, lambda: embedder, min_score=0.0)
    items = load_eval_set(ROOT / "data" / "policy_eval.yaml")

    def search(query, top_k):
        result = service.search(query, top_k=top_k)
        assert "error" not in result
        return result["passages"]

    report = evaluate(search, items, top_k=5)

    # Embedder băm không có ngữ nghĩa nên KHÔNG khẳng định ngưỡng recall; chỉ kiểm tra hình dạng và miền giá trị.
    assert report.single_count == sum(1 for item in items if len(item.expect) == 1) >= 20
    assert report.multi_count == sum(1 for item in items if len(item.expect) >= 2) >= 4
    assert report.out_of_scope_count == sum(1 for item in items if not item.expect) >= 4
    assert report.in_scope_count == report.single_count + report.multi_count
    assert report.cutoffs == (1, 3, 5)
    for table in (report.recall_doc, report.recall_section):
        assert set(table) == {1, 3, 5}
        assert all(0.0 <= value <= 1.0 for value in table.values())
        assert table[1] <= table[3] <= table[5]
    assert 0.0 <= report.mrr <= 1.0
    assert report.no_result_count == 0
    assert len(report.in_scope_top1) == report.in_scope_count
    assert len(report.out_of_scope_top1) == report.out_of_scope_count
    assert format_report(report)


# ------------------------------------------------------------------------------------------------ main()

def test_main_without_gemini_key_exits_2_and_prints_no_secret(monkeypatch, capsys):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "milvus_token", SECRETS[0])
    monkeypatch.setattr(settings, "milvus_uri", SECRETS[2])

    code = eval_retrieval.main([])

    captured = capsys.readouterr()
    assert code == 2
    assert "GEMINI_API_KEY" in captured.err
    assert not any(secret in captured.out + captured.err for secret in SECRETS)


def test_main_with_an_invalid_eval_file_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(settings, "gemini_api_key", SECRETS[1])
    bad = write(tmp_path, "- question: x\n")

    code = eval_retrieval.main(["--eval", str(bad)])

    captured = capsys.readouterr()
    assert code == 2
    assert SECRETS[1] not in captured.out + captured.err


def test_main_exits_2_when_the_store_cannot_be_reached(monkeypatch, capsys):
    monkeypatch.setattr(settings, "gemini_api_key", SECRETS[1])

    def unreachable(query, top_k):
        raise SearchFailed("Kho chính sách chưa được nạp hoặc không kết nối được.")

    monkeypatch.setattr(eval_retrieval, "_build_search", lambda: unreachable)

    code = eval_retrieval.main([])

    captured = capsys.readouterr()
    assert code == 2
    assert "chưa được nạp" in captured.err
    assert SECRETS[1] not in captured.out + captured.err


def test_main_exits_2_when_the_store_is_empty(monkeypatch, capsys):
    monkeypatch.setattr(settings, "gemini_api_key", SECRETS[1])
    monkeypatch.setattr(eval_retrieval, "_build_search", lambda: lambda query, top_k: [])

    code = eval_retrieval.main([])

    assert code == 2
    assert "ingest-policies" in capsys.readouterr().err


def test_main_prints_the_report_and_exits_0(monkeypatch, capsys):
    monkeypatch.setattr(settings, "gemini_api_key", SECRETS[1])
    monkeypatch.setattr(eval_retrieval, "_build_search", lambda: lambda query, top_k: [p("zzz", "X", 0.5)])

    code = eval_retrieval.main(["--top-k", "3"])

    out = capsys.readouterr().out
    assert code == 0
    assert "recall@1" in out and "MRR" in out and "recall@5" not in out
    assert SECRETS[1] not in out


@pytest.mark.parametrize("value", ["0", "9", "x"])
def test_main_rejects_a_top_k_outside_1_to_8(value, capsys):
    with pytest.raises(SystemExit) as raised:
        eval_retrieval.main(["--top-k", value])

    assert raised.value.code == 2
