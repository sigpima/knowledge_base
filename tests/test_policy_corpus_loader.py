"""Bộ đọc corpus chính sách: front matter YAML + thân Markdown."""
import hashlib
import unicodedata
from pathlib import Path

import pytest

from app.domains.policy.application.services.corpus import (
    PolicyDocument,
    PolicyFileError,
    load_policy_dir,
    load_policy_file,
)

VALID = """---
slug: bao-hanh-son-ngoai-that
title: Chính sách bảo hành sơn ngoại thất
doc_type: warranty
applies_to: [son-ngoai-that, son-lot]
---
# Bảo hành

Thời hạn bảo hành là 5 năm.
"""


def write(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


def test_valid_file(tmp_path):
    doc = load_policy_file(write(tmp_path, "a.md", VALID))
    assert isinstance(doc, PolicyDocument)
    assert doc.front.slug == "bao-hanh-son-ngoai-that"
    assert doc.front.title == "Chính sách bảo hành sơn ngoại thất"
    assert doc.front.doc_type == "warranty"
    assert doc.front.applies_to == ["son-ngoai-that", "son-lot"]
    assert doc.source_name == "a.md"
    assert doc.body.startswith("# Bảo hành")
    assert doc.body.endswith("5 năm.")
    assert "slug:" not in doc.body
    assert "---" not in doc.body


def test_applies_to_defaults_to_empty(tmp_path):
    text = "---\nslug: abc\ntitle: T\ndoc_type: technical\n---\nNội dung\n"
    assert load_policy_file(write(tmp_path, "a.md", text)).front.applies_to == []


def test_missing_front_matter(tmp_path):
    with pytest.raises(PolicyFileError) as exc:
        load_policy_file(write(tmp_path, "a.md", "# Chỉ có thân\n\nKhông có front matter.\n"))
    assert exc.value.errors
    assert "a.md" in str(exc.value)


def test_unterminated_front_matter(tmp_path):
    with pytest.raises(PolicyFileError):
        load_policy_file(write(tmp_path, "a.md", "---\nslug: abc\ntitle: T\ndoc_type: technical\nThân\n"))


def test_invalid_yaml(tmp_path):
    with pytest.raises(PolicyFileError):
        load_policy_file(write(tmp_path, "a.md", "---\nslug: [abc\n---\nThân\n"))


def test_front_matter_not_a_mapping(tmp_path):
    with pytest.raises(PolicyFileError):
        load_policy_file(write(tmp_path, "a.md", "---\n- a\n- b\n---\nThân\n"))


def test_invalid_doc_type(tmp_path):
    with pytest.raises(PolicyFileError) as exc:
        load_policy_file(write(tmp_path, "a.md", VALID.replace("doc_type: warranty", "doc_type: other")))
    assert any("doc_type" in e for e in exc.value.errors)


@pytest.mark.parametrize("bad_slug", ["Sai Slug", "Sai-Slug", "-abc", "abc-", "a--b", "a_b", "đúng"])
def test_invalid_slug(tmp_path, bad_slug):
    text = VALID.replace("slug: bao-hanh-son-ngoai-that", f'slug: "{bad_slug}"')
    with pytest.raises(PolicyFileError) as exc:
        load_policy_file(write(tmp_path, "a.md", text))
    assert any("slug" in e for e in exc.value.errors)


@pytest.mark.parametrize("title", ['""', '"   "'])
def test_empty_title(tmp_path, title):
    text = VALID.replace("title: Chính sách bảo hành sơn ngoại thất", f"title: {title}")
    with pytest.raises(PolicyFileError) as exc:
        load_policy_file(write(tmp_path, "a.md", text))
    assert any("title" in e for e in exc.value.errors)


def test_unknown_field_forbidden(tmp_path):
    with pytest.raises(PolicyFileError) as exc:
        load_policy_file(write(tmp_path, "a.md", VALID.replace("---\n#", "extra: 1\n---\n#", 1)))
    assert any("extra" in e for e in exc.value.errors)


def test_nfd_and_nfc_give_same_hash_and_nfc_body(tmp_path):
    nfc_dir, nfd_dir = tmp_path / "nfc", tmp_path / "nfd"
    nfc_dir.mkdir()
    nfd_dir.mkdir()
    nfc_text = unicodedata.normalize("NFC", VALID)
    nfd_text = unicodedata.normalize("NFD", VALID)
    assert nfc_text != nfd_text
    nfc = load_policy_file(write(nfc_dir, "a.md", nfc_text))
    nfd = load_policy_file(write(nfd_dir, "a.md", nfd_text))
    assert nfc.content_hash == nfd.content_hash
    assert nfd.body == unicodedata.normalize("NFC", nfd.body)
    assert nfd.body == nfc.body
    assert nfd.front.title == nfc.front.title


def test_content_hash_is_sha256_of_nfc_text(tmp_path):
    doc = load_policy_file(write(tmp_path, "a.md", VALID))
    expected = hashlib.sha256(unicodedata.normalize("NFC", VALID).encode("utf-8")).hexdigest()
    assert doc.content_hash == expected


def test_changing_one_body_character_changes_hash(tmp_path):
    a = load_policy_file(write(tmp_path, "a.md", VALID))
    b = load_policy_file(write(tmp_path, "b.md", VALID.replace("5 năm", "6 năm")))
    assert a.content_hash != b.content_hash


def test_load_dir_orders_by_name_and_ignores_other_files(tmp_path):
    write(tmp_path, "b.md", VALID.replace("bao-hanh-son-ngoai-that", "bbb"))
    write(tmp_path, "a.md", VALID.replace("bao-hanh-son-ngoai-that", "aaa"))
    write(tmp_path, "notes.txt", "không phải markdown")
    docs = load_policy_dir(tmp_path)
    assert [d.source_name for d in docs] == ["a.md", "b.md"]
    assert [d.front.slug for d in docs] == ["aaa", "bbb"]


def test_load_dir_duplicate_slug_names_both_files(tmp_path):
    write(tmp_path, "one.md", VALID)
    write(tmp_path, "two.md", VALID)
    with pytest.raises(PolicyFileError) as exc:
        load_policy_dir(tmp_path)
    message = str(exc.value)
    assert "one.md" in message and "two.md" in message
    assert any("one.md" in e and "two.md" in e for e in exc.value.errors)


def test_load_dir_propagates_invalid_file(tmp_path):
    write(tmp_path, "ok.md", VALID)
    write(tmp_path, "bad.md", "không có front matter")
    with pytest.raises(PolicyFileError) as exc:
        load_policy_dir(tmp_path)
    assert "bad.md" in str(exc.value)
