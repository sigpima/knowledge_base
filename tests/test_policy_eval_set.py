"""Bộ câu hỏi đánh giá truy xuất (`data/policy_eval.yaml`): đúng cấu trúc, khớp corpus, đủ phủ. Không cần khoá hay DB."""
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pytest

from app.domains.policy.application.services.corpus import load_policy_dir
from scripts.eval_retrieval import DEFAULT_EVAL_PATH, load_eval_set

ROOT = Path(__file__).parent.parent
CORPUS_DIR = ROOT / "data" / "policies"


@pytest.fixture(scope="module")
def items():
    return load_eval_set(ROOT / "data" / "policy_eval.yaml")


@pytest.fixture(scope="module")
def corpus():
    return load_policy_dir(CORPUS_DIR)


def _h2_titles(body: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"^## (.+)$", body, flags=re.MULTILINE)]


def _norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def test_default_eval_path_is_the_committed_file():
    assert DEFAULT_EVAL_PATH == ROOT / "data" / "policy_eval.yaml"
    assert DEFAULT_EVAL_PATH.is_file()


def test_set_has_enough_questions_of_each_kind(items):
    single = [item for item in items if len(item.expect) == 1]
    multi = [item for item in items if len(item.expect) >= 2]
    out_of_scope = [item for item in items if not item.expect]

    assert len(items) >= 28
    assert len(single) >= 20
    assert len(multi) >= 4
    assert len(out_of_scope) >= 4
    assert len(single) + len(multi) + len(out_of_scope) == len(items)


def test_every_expectation_points_at_a_real_slug_and_an_exact_h2_title(items, corpus):
    sections = {doc.front.slug: _h2_titles(doc.body) for doc in corpus}
    problems = []
    for item in items:
        for expectation in item.expect:
            if expectation.slug not in sections:
                problems.append(f"{item.question!r}: slug lạ {expectation.slug!r}")
            elif expectation.section not in sections[expectation.slug]:
                problems.append(f"{item.question!r}: {expectation.section!r} không phải tiêu đề ## của {expectation.slug}")

    assert problems == []


def test_every_policy_document_is_covered_by_a_single_source_question(items, corpus):
    covered = {item.expect[0].slug for item in items if len(item.expect) == 1}

    assert covered == {doc.front.slug for doc in corpus}


def test_multi_source_questions_need_two_different_documents(items):
    for item in items:
        if len(item.expect) >= 2:
            assert len({e.slug for e in item.expect}) == len(item.expect), item.question


def test_no_duplicate_questions(items):
    counts = Counter(_norm(item.question) for item in items)

    assert [question for question, n in counts.items() if n > 1] == []


def test_no_question_copies_a_section_or_document_title(items, corpus):
    titles = {_norm(doc.front.title) for doc in corpus}
    for doc in corpus:
        titles.update(_norm(title) for title in _h2_titles(doc.body))

    copied = [item.question for item in items if _norm(item.question).rstrip("?").strip() in titles]

    assert copied == []


def test_questions_are_questions_with_reasonable_length(items):
    for item in items:
        assert item.question.strip().endswith("?"), item.question
        assert 15 <= len(item.question) <= 300, item.question
