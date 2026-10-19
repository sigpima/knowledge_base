from pathlib import Path

from scripts.check_scrub import scan

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_scan_flags_default_forbidden_words(tmp_path):
    (tmp_path / "a.txt").write_text("hello\nsơn Jotun cao cấp\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("x = 1\npath = '/home/someone/project'\n", encoding="utf-8")

    hits = scan(tmp_path)

    assert sorted((path.name, line) for path, line, _ in hits) == [("a.txt", 2), ("b.py", 2)]


def test_scan_ignores_clean_files(tmp_path):
    (tmp_path / "ok.md").write_text("Sơn Việt Demo Co. báo giá chống thấm\n", encoding="utf-8")

    assert scan(tmp_path) == []


def test_scan_flags_forbidden_file_names(tmp_path):
    (tmp_path / "dulux_notes.txt").write_text("clean content\n", encoding="utf-8")

    assert [path.name for path, _, _ in scan(tmp_path)] == ["dulux_notes.txt"]


def test_scan_reads_extra_patterns_from_local_file(tmp_path):
    (tmp_path / ".scrub-patterns").write_text("# chú thích\nzzz-secret\n", encoding="utf-8")
    (tmp_path / "a.txt").write_text("line one\nthe ZZZ-Secret word\n", encoding="utf-8")

    assert [(path.name, line) for path, line, _ in scan(tmp_path)] == [("a.txt", 2)]


def test_repo_is_clean():
    assert scan(REPO_ROOT) == []
